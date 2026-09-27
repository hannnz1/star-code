import hashlib
import io
import json
import re

from pypdf import PdfReader


class DocumentTools:
    def __init__(self, context, files):
        self.ctx, self.files = context, files

    async def read(self, args, call_id):
        path = self.files.policy.resolve(args["path"], must_exist=True)
        raw = self.files.read_bytes(args["path"])
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            content = raw.decode("utf-8-sig")
        elif suffix == ".pdf":
            try:
                reader = PdfReader(io.BytesIO(raw))
                if reader.is_encrypted:
                    raise ValueError("Encrypted PDF is not supported")
                if len(reader.pages) > 200:
                    raise ValueError("PDF exceeds 200 pages")
                content = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception:  # noqa: BLE001 -- malformed third-party PDFs can raise many parser exceptions; never report extraction success.
                raise ValueError("PDF could not be parsed or is encrypted") from None
            if not content.strip():
                raise ValueError("PDF has no extractable text; OCR is not supported in this version")
        else:
            raise ValueError("Supported documents: TXT, Markdown and text-based PDF")
        self.ctx.cp["document_reads"] = self.ctx.cp.get("document_reads", 0) + 1
        return json.dumps({"path": args["path"], "sha256": hashlib.sha256(raw).hexdigest(),
                           "text": self.ctx.safe(content[:200000]), "truncated": len(content) > 200000}, ensure_ascii=False)

    async def organize(self, args, call_id):
        source = self.files.policy.resolve(args["path"], must_exist=True)
        if source.suffix.lower() not in {".txt", ".md", ".markdown", ".pdf"}:
            raise ValueError("Only supported document formats can be organized")
        category = args["category"].strip()
        if not category or category in {".", ".."} or re.search(r'[/\\:*?"<>|\x00]', category):
            raise ValueError("Category must be a directory name")
        relative = source.relative_to(self.ctx.workspace)
        if relative.parts[0] == "muse-output":
            raise ValueError("Select an original source, not an existing output copy")
        data = self.files.read_bytes(args["path"])
        digest = hashlib.sha256(data).hexdigest()
        destination = self.files.policy.resolve(str(self.ctx.workspace / "muse-output" / category / relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            destination = destination.with_name(f"{destination.stem}-{digest[:12]}{destination.suffix}")
        self.files.policy.resolve(str(destination))
        self.ctx.check()
        try:
            with destination.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                raise ValueError("Conflicting output file; original and existing copy were preserved")
        return json.dumps({"source": relative.as_posix(), "copy": destination.relative_to(self.ctx.workspace).as_posix(),
                           "sha256": digest, "original_preserved": hashlib.sha256(source.read_bytes()).hexdigest() == digest}, ensure_ascii=False)
