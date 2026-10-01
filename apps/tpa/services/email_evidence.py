"""Read email containers and preserve the cells of member tables."""
import io
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

from .schemas import MemberEvidence


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif self.stack:
            table = self.stack[-1]
            if tag == "tr":
                table["row"] = []
            elif tag in {"td", "th"}:
                table["cell"] = []
            elif tag == "br" and table["cell"] is not None:
                table["cell"].append(" ")

    def handle_data(self, data):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append(data)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        table = self.stack[-1]
        if tag in {"td", "th"} and table["cell"] is not None:
            if table["row"] is not None:
                table["row"].append(" ".join("".join(table["cell"]).split()))
            table["cell"] = None
        elif tag == "tr" and table["row"] is not None:
            table["rows"].append(table["row"])
            table["row"] = None
        elif tag == "table":
            self.tables.append(self.stack.pop()["rows"])


def member_rows_from_html(html):
    parser = _Tables()
    parser.feed(html or "")
    aliases = {"dob": "date_of_birth", "name": "full_name", "sex": "gender",
               "civil_number": "national_id", "civil_id": "national_id", "employee_no": "employee_id"}
    fields = set(MemberEvidence.model_fields) - {"confidence"}
    result = []
    for table in parser.tables:
        headers = None
        for cells in table:
            candidate = [aliases.get(key, key) for key in (
                "_".join(cell.lower().replace("-", " ").split()) for cell in cells
            )]
            if len(fields.intersection(candidate)) >= 2:
                headers = candidate
                continue
            if headers and len(cells) == len(headers) and any(cells):
                row = {key: value for key, value in zip(headers, cells) if key}
                if any(row.get(key) for key in ("employee_id", "member_id", "national_id", "passport_number", "first_name", "full_name")):
                    result.append(row)
    return result


def read_email_evidence(name, content):
    if Path(name).suffix.lower() == ".msg":
        try:
            import extract_msg
        except ImportError as exc:
            raise RuntimeError("Outlook MSG intake requires extract-msg from requirements.txt.") from exc
        with extract_msg.Message(io.BytesIO(content)) as message:
            html = message.htmlBody or b""
            return {
                "subject": message.subject or "", "sender": message.sender or "",
                "recipient": message.to or "", "body_text": message.body or "",
                "body_html": html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html,
                "attachments": [
                    {"name": Path((item.longFilename or item.shortFilename or "attachment").replace("\\", "/")).name,
                     "content": item.data, "content_type": ""}
                    for item in message.attachments if isinstance(item.data, bytes)
                ],
            }
    message = BytesParser(policy=policy.default).parsebytes(content)
    text, html, attachments = [], [], []
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            attachments.append({"name": part.get_filename() or "attachment",
                                "content": part.get_payload(decode=True) or b"",
                                "content_type": part.get_content_type()})
        elif part.get_content_type() == "text/html":
            html.append(str(part.get_content()))
        elif part.get_content_type() == "text/plain":
            text.append(str(part.get_content()))
    return {"subject": str(message.get("Subject") or ""), "sender": str(message.get("From") or ""),
            "recipient": str(message.get("To") or ""), "body_text": "\n".join(text),
            "body_html": "\n".join(html), "attachments": attachments}
