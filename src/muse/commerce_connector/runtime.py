"""Explicit Linux-only publication service startup. Creates no grant or report."""
import os
import platform
import stat
import time
from pathlib import Path

from muse.commerce.environment import validate_lock
from muse.commerce.errors import CommerceFailure
from muse.commerce.merchant_approval import MerchantReleaseApprovalRepository
from muse.commerce.merchant_journal import MerchantReleaseJournal
from muse.commerce.merchant_review import MerchantPublicationService
from muse.commerce.repository import CommerceRepository
from muse.commerce_connector.merchant_authorization import MerchantReleaseAuthority
from muse.commerce_connector.merchant_publisher import MerchantReleasePublisher
from muse.commerce_connector.operation_ledger import OperationLedger
from muse.tasks.repository import TaskRepository


def create_reference_service(*, runtime_database, private_directory, versions_lock, woocommerce_archive, ports):
    """Explicit host-only startup; requires offline verified assets and Linux."""
    from muse.commerce.reference_environment import load_reference_assets
    from muse.commerce.reference_jobs import ReferenceJobRepository
    from muse.commerce.reference_runner import DockerReferenceRunner
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService

    database, directory = Path(runtime_database).absolute(), Path(private_directory).absolute()
    try:
        if platform.system() != 'Linux' or os.name != 'posix':
            raise ValueError()
        validate_lock(versions_lock)
        if (not database.is_file() or not directory.is_dir()
                or any(path.is_symlink() or path.is_junction() for path in (database, directory, *database.parents, *directory.parents))):
            raise ValueError()
        info = directory.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError()
        bundle = load_reference_assets(versions_lock, woocommerce_archive)
    except (ValueError, OSError, TypeError, AttributeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
    runtime = TaskRepository(database)
    jobs = ReferenceJobRepository(CommerceRepository(runtime))
    try:
        return ReferenceEnvironmentService(jobs, DockerReferenceRunner(jobs, directory, versions_lock), bundle, ports=ports)
    except BaseException:
        runtime.db.engine.dispose()
        raise


def create_publication_service(connections, execution_secrets, *, runtime_database, private_directory,
                               versions_lock, clock=time.time):
    database, directory = Path(runtime_database).absolute(), Path(private_directory).absolute()
    try:
        if platform.system() != 'Linux':
            raise ValueError()
        validate_lock(versions_lock)
        if (not database.is_file() or not directory.is_dir() or set(connections) != set(execution_secrets)
                or any(key != value.connection_id for key, value in connections.items())
                or any(not isinstance(secret, bytes) or not 32 <= len(secret) <= 1024 for secret in execution_secrets.values())
                or any(path.is_symlink() or path.is_junction() for path in (database, directory, *database.parents, *directory.parents))):
            raise ValueError()
        if os.name == 'posix':
            info = directory.stat()
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError()
        ledger_path = directory / 'publication-ledger.sqlite'
        if ledger_path.is_symlink() or ledger_path.is_junction():
            raise ValueError()
    except (ValueError, OSError, TypeError, AttributeError):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
    runtime = TaskRepository(database)
    approvals = MerchantReleaseApprovalRepository(CommerceRepository(runtime), clock=clock)
    ledger = OperationLedger(ledger_path)
    publishers = {key: MerchantReleasePublisher(connection, MerchantReleaseJournal(approvals, ledger),
        MerchantReleaseAuthority(execution_secrets[key], clock=clock), versions_lock=versions_lock, execution_enabled=True)
        for key, connection in connections.items()}

    def resolve(identity):
        if identity not in publishers:
            raise CommerceFailure('NOT_FOUND', 404)
        return publishers[identity]
    return MerchantPublicationService(approvals, resolve)


class VerificationHostLease:
    """Held OS lock; only its owner may account a prior process's claims."""
    def __init__(self, directory):
        self.fd = None
        try:
            if platform.system() != 'Linux' or os.name != 'posix':
                raise ValueError()
            import fcntl
            root = Path(directory).absolute()
            if (not root.is_dir() or any(p.is_symlink() or p.is_junction() for p in (root, *root.parents))
                    or root.stat().st_uid != os.getuid() or stat.S_IMODE(root.stat().st_mode) != 0o700):
                raise ValueError()
            fd = os.open(root / 'verification.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            self.fd = fd
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ValueError, OSError, AttributeError):
            self.close()
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def create_verification_service(connections, reference):
    """Wire fixed producers to the shared journal, never arbitrary handlers."""
    import re

    from muse.commerce.buyer_probe import BuyerProbeRepository
    from muse.commerce.buyer_sender import SyntheticBuyer
    from muse.commerce.buyer_verification_stage import BuyerVerificationStage
    from muse.commerce.isolation import DockerCodingSession
    from muse.commerce.readback_verification_stage import ReadbackVerificationStage
    from muse.commerce.reference_verification_stage import ReferenceVerificationStage
    from muse.commerce.source_capture_stage import SourceCaptureStage
    from muse.commerce.staging_journal import StagingReleaseJournal
    from muse.commerce.staging_verification_stage import StagingVerificationStage
    from muse.commerce.verification_jobs import VerificationJobRepository
    from muse.commerce.verification_runtime import VerificationRuntime
    from muse.commerce.verification_service import CommerceVerificationService
    from muse.commerce_connector.reference_service import ReferenceEnvironmentService
    from muse.commerce_connector.staging_authorization import StagingReleaseAuthority
    from muse.commerce_connector.staging_publisher import StagingReleasePublisher

    if type(reference) is not ReferenceEnvironmentService:
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
    lock, root = reference.runner.lock, reference.runner.root
    validate_lock(lock)
    if not re.fullmatch(r'[a-zA-Z0-9._/:-]+@sha256:[a-f0-9]{64}', lock.get('images', {}).get('coding', '')):
        raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
    lease = VerificationHostLease(root)
    try:
        jobs = VerificationJobRepository(reference.jobs.repo)
        source = SourceCaptureStage(jobs, reference, lambda: DockerCodingSession(root, lock))
        ledger_path = root / 'verification-ledger.sqlite'
        if ledger_path.is_symlink() or ledger_path.is_junction():
            raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
        ledger = OperationLedger(ledger_path)

        def publisher(connection):
            job = reference.jobs.read(connection.project_id, connection.connection_id[4:])
            if reference.resolve_connection(connection.connection_id, connection.project_id) != connection:
                raise CommerceFailure('REVIEW_STALE')
            secret = reference.runner._read_private(job, 'connection.json')['execution_secret'].encode()
            return StagingReleasePublisher(connection, StagingReleaseJournal(source.sources, ledger),
                StagingReleaseAuthority(secret), versions_lock=lock, execution_enabled=True)

        buyer = SyntheticBuyer(BuyerProbeRepository(jobs.repo), reference.jobs, reference.runner, source.sources)
        runtime = VerificationRuntime(jobs, reference=ReferenceVerificationStage(jobs, reference), source_capture=source,
            staging=StagingVerificationStage(jobs, source, publisher), buyer=BuyerVerificationStage(jobs, source, buyer),
            browser=ReadbackVerificationStage(jobs, source, 'browser'), facts=ReadbackVerificationStage(jobs, source, 'facts'))
        service = CommerceVerificationService(runtime, connections)
        service.host_lease = lease
        return service
    except BaseException:
        lease.close()
        raise
