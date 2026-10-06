"""Start with python -m muse.commerce_connector; never run as the coding UID."""
import argparse
import json
from pathlib import Path

import uvicorn

from muse.commerce.errors import CommerceFailure
from muse.commerce_connector.api import create_connector_app
from muse.commerce_connector.secret_store import (
    load_connector_config,
    load_execution_secrets,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--enable-publication', action='store_true', help='Enable fixed approved v4 commands; requires verified Linux deployment')
    parser.add_argument('--runtime-database', type=Path, help='Existing MUSE runtime database, outside all agent mounts')
    parser.add_argument('--versions-lock', type=Path, help='Verified compatible Linux image/version manifest')
    parser.add_argument('--enable-reference-environments', action='store_true', help='Enable fixed isolated preview jobs; requires verified Linux deployment')
    parser.add_argument('--reference-private-directory', type=Path, help='Existing owner-only host directory outside agent mounts')
    parser.add_argument('--woocommerce-archive', type=Path, help='Offline Woo ZIP matching versions-lock SHA256')
    parser.add_argument('--reference-port-start', type=int, default=63800)
    parser.add_argument('--reference-port-count', type=int, default=4)
    parser.add_argument('--enable-verification', action='store_true', help='Run fixed six-stage verification; requires reference environments and pinned coding image')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Invalid port')
    if args.enable_verification and not args.enable_reference_environments:
        parser.error('--enable-verification requires --enable-reference-environments')
    publication = reference = verification = None
    try:
        connections, token = load_connector_config(args.config)
        if args.enable_publication or args.enable_reference_environments:
            if args.runtime_database is None or args.versions_lock is None:
                raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
            try:
                lock = json.loads(args.versions_lock.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503) from None
            if args.enable_reference_environments:
                if (args.reference_private_directory is None or args.woocommerce_archive is None
                        or not 1 <= args.reference_port_count <= 32 or args.reference_port_start < 1024
                        or args.reference_port_start + args.reference_port_count > 65536
                        or args.port in range(args.reference_port_start, args.reference_port_start + args.reference_port_count)):
                    raise CommerceFailure('EXECUTION_BOUNDARY_UNAVAILABLE', 503)
                from muse.commerce_connector.runtime import create_reference_service
                reference = create_reference_service(runtime_database=args.runtime_database,
                    private_directory=args.reference_private_directory, versions_lock=lock,
                    woocommerce_archive=args.woocommerce_archive,
                    ports=tuple(range(args.reference_port_start, args.reference_port_start + args.reference_port_count)))
            if args.enable_publication:
                from muse.commerce_connector.runtime import create_publication_service
                publication = create_publication_service(connections, load_execution_secrets(args.config),
                    runtime_database=args.runtime_database, private_directory=args.config.parent, versions_lock=lock)
            if args.enable_verification:
                from muse.commerce_connector.runtime import create_verification_service
                verification = create_verification_service(connections, reference)
    except CommerceFailure as error:
        if reference is not None:
            reference.jobs.db.engine.dispose()
        parser.exit(2, error.public.code + ': ' + error.public.message + '\n')
    # A supervised reverse proxy / namespace boundary is required for remote clients.
    try:
        uvicorn.run(create_connector_app(connections, token=token, publication=publication, reference=reference, verification=verification), host='127.0.0.1', port=args.port,
                    access_log=False)
    finally:
        if verification is not None:
            verification.host_lease.close()
        if publication is not None:
            publication.approvals.db.engine.dispose()
        if reference is not None:
            reference.jobs.db.engine.dispose()


if __name__ == '__main__':
    main()
