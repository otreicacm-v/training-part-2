# ADR-018: DMS Security and Storage Enhancements

## Status

**Accepted** — modules are planned, not yet implemented

**Date:** 2025-12-14

### Implementation Summary

All modules described in this ADR (`trn_dms`, `trn_attachment_av_scan`, `trn_audit`, `trn_storage_backend`) are **planned but not yet implemented**. The architecture remains valid for future development.

## Context

The Document Management System (`trn_dms`) provides centralized document storage with hierarchical organization. A security and architecture review has identified several areas for improvement:

### Current State Analysis

| Feature | Current State | Risk Level |
|---------|---------------|------------|
| Storage Backend | Hardcoded Odoo ir.attachment | Medium - No cloud storage flexibility |
| File Type Validation | MIME type detection only | High - No executable restrictions |
| File Size Limits | None enforced | Medium - DoS vulnerability |
| Antivirus Scanning | Not implemented | High - Malware upload risk |
| Download Audit | Not implemented | Medium - Compliance gap |
| Document Versioning | Not implemented | Low - Feature gap |

### Current DMS Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        trn_dms                              │
├─────────────────────────────────────────────────────────────┤
│  trn.dms.file          │ trn.dms.directory │ trn.dms.category│
│  ├── content (binary)  │ ├── name          │ ├── name        │
│  ├── checksum (SHA512) │ ├── parent_id     │ └── file_ids    │
│  ├── mimetype          │ └── file_ids      │                 │
│  └── size              │                   │                 │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   Odoo ir.attachment  │
              │   (file system only)  │
              └───────────────────────┘
```

### Existing Security Patterns

The `trn_verifiable_credentials` module demonstrates good security patterns:
- Input validation with size limits (`MAX_CREDENTIAL_SIZE = 1MB`)
- Rate limiting decorator
- Constant-time comparison for timing attack prevention
- Audit logging

The `trn_audit` module provides extensible audit trail:
- Automatic CRUD auditing via decorator
- `log_lifecycle_action()` for custom events
- Configurable action flags per model

### Requirements

1. **Security**: Prevent malware uploads across all Odoo attachments
2. **Flexibility**: Support cloud storage backends (S3, Azure, MinIO)
3. **Compliance**: Audit trail for document access
4. **Usability**: Better upload experience, document versioning

### Constraints

- **License**: Must be LGPL-3 (cannot use OCA's AGPL modules like `storage_backend`)
- **Async**: File scanning must not block uploads
- **Odoo-wide**: AV scanning should protect all attachments, not just DMS

## Decision

We will implement a modular enhancement strategy with the following components:

### 1. System-Wide Antivirus Scanning (`trn_attachment_av_scan`)

Extend `ir.attachment` to provide Odoo-wide malware protection via async scanning.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Attachment AV Scan Flow                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   User Upload                                                           │
│       │                                                                 │
│       ▼                                                                 │
│   ┌─────────────────────┐                                               │
│   │  ir.attachment      │                                               │
│   │  create()           │                                               │
│   │  ├── scan_status:   │                                               │
│   │  │   'pending'      │◄────── Immediate (no blocking)                │
│   │  └── scan_date: -   │                                               │
│   └─────────────────────┘                                               │
│       │                                                                 │
│       ▼ (queue_job)                                                     │
│   ┌─────────────────────┐         ┌─────────────────────┐               │
│   │  _scan_attachment() │────────►│  Scanner Backend    │               │
│   │  (async)            │         │  ├── ClamAV daemon  │               │
│   └─────────────────────┘         │  ├── ClamAV socket  │               │
│       │                           │  ├── REST API       │               │
│       ▼                           │  └── (extensible)   │               │
│   ┌─────────────────────┐         └─────────────────────┘               │
│   │  scan_status:       │                                               │
│   │  'clean' | 'infected' | 'error'                                     │
│   │  scan_result: JSON  │                                               │
│   │  scan_date: now()   │                                               │
│   └─────────────────────┘                                               │
│       │                                                                 │
│       ▼ (if infected)                                                   │
│   ┌─────────────────────┐                                               │
│   │  Quarantine Action  │                                               │
│   │  ├── Move to quarantine dir                                         │
│   │  ├── Notify admins                                                  │
│   │  └── Log security event                                             │
│   └─────────────────────┘                                               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Scanner Backend Interface

```python
class AVScannerBackend(models.Model):
    _name = "trn.av.scanner.backend"
    _description = "Antivirus Scanner Backend"

    name = fields.Char(required=True)
    backend_type = fields.Selection([
        ("clamd_socket", "ClamAV Socket"),
        ("clamd_network", "ClamAV Network"),
        ("rest_api", "REST API (VirusTotal, etc.)"),
    ], required=True, default="clamd_socket")
    is_active = fields.Boolean(default=True)

    # ClamAV settings
    clamd_socket_path = fields.Char(default="/var/run/clamav/clamd.sock")
    clamd_host = fields.Char(default="localhost")
    clamd_port = fields.Integer(default=3310)

    # REST API settings (for cloud scanners)
    api_url = fields.Char()
    api_key = fields.Char()

    # Limits
    max_file_size_mb = fields.Integer(
        default=100,
        help="Skip scanning files larger than this (MB)"
    )
    scan_timeout_seconds = fields.Integer(default=60)

    def scan_binary(self, binary_data, filename=None):
        """
        Scan binary data for malware.

        Returns:
            dict: {
                'status': 'clean' | 'infected' | 'error',
                'threat_name': str or None,
                'details': dict
            }
        """
        self.ensure_one()
        if self.backend_type == "clamd_socket":
            return self._scan_clamd_socket(binary_data)
        elif self.backend_type == "clamd_network":
            return self._scan_clamd_network(binary_data)
        elif self.backend_type == "rest_api":
            return self._scan_rest_api(binary_data, filename)
        raise NotImplementedError(f"Backend type {self.backend_type} not implemented")

    def _scan_clamd_socket(self, binary_data):
        """Scan using ClamAV Unix socket."""
        import pyclamd

        try:
            cd = pyclamd.ClamdUnixSocket(self.clamd_socket_path)
            result = cd.scan_stream(binary_data)

            if result is None:
                return {"status": "clean", "threat_name": None, "details": {}}

            # Result format: {'stream': ('FOUND', 'Threat.Name')}
            status, threat = result.get("stream", (None, None))
            return {
                "status": "infected" if status == "FOUND" else "error",
                "threat_name": threat,
                "details": {"raw_result": result}
            }
        except Exception as e:
            _logger.exception("ClamAV scan failed")
            return {"status": "error", "threat_name": None, "details": {"error": str(e)}}
```

#### ir.attachment Extension

```python
class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    scan_status = fields.Selection([
        ("pending", "Pending Scan"),
        ("scanning", "Scanning"),
        ("clean", "Clean"),
        ("infected", "Infected"),
        ("error", "Scan Error"),
        ("skipped", "Skipped"),
    ], default="pending", index=True)
    scan_date = fields.Datetime()
    scan_result = fields.Text()  # JSON details
    threat_name = fields.Char()
    is_quarantined = fields.Boolean(default=False)

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)

        # Queue scan for binary attachments
        to_scan = attachments.filtered(
            lambda a: a.datas and not a.url and a.scan_status == "pending"
        )
        if to_scan:
            to_scan.with_delay(
                priority=5,
                description="Antivirus scan"
            )._scan_for_malware()

        return attachments

    def _scan_for_malware(self):
        """Async job to scan attachments for malware."""
        scanner = self.env["trn.av.scanner.backend"].search([
            ("is_active", "=", True)
        ], limit=1)

        if not scanner:
            self.write({"scan_status": "skipped", "scan_date": fields.Datetime.now()})
            return

        for attachment in self:
            attachment.scan_status = "scanning"

            # Check size limit
            if attachment.file_size > (scanner.max_file_size_mb * 1024 * 1024):
                attachment.write({
                    "scan_status": "skipped",
                    "scan_date": fields.Datetime.now(),
                    "scan_result": json.dumps({"reason": "File too large"})
                })
                continue

            try:
                binary_data = base64.b64decode(attachment.datas)
                result = scanner.scan_binary(binary_data, attachment.name)

                attachment.write({
                    "scan_status": result["status"],
                    "scan_date": fields.Datetime.now(),
                    "threat_name": result.get("threat_name"),
                    "scan_result": json.dumps(result.get("details", {}))
                })

                if result["status"] == "infected":
                    attachment._quarantine()

            except Exception as e:
                _logger.exception("Scan failed for attachment %s", attachment.id)
                attachment.write({
                    "scan_status": "error",
                    "scan_date": fields.Datetime.now(),
                    "scan_result": json.dumps({"error": str(e)})
                })

    def _quarantine(self):
        """Move infected attachment to quarantine."""
        self.ensure_one()
        self.is_quarantined = True

        # Clear the binary data or move to quarantine storage
        # Keep metadata for investigation
        quarantine_data = {
            "original_name": self.name,
            "threat": self.threat_name,
            "quarantined_at": fields.Datetime.now(),
            "uploaded_by": self.create_uid.id,
        }

        # Log security event
        _logger.warning(
            "SECURITY: Malware quarantined - attachment_id=%s, threat=%s, user=%s",
            self.id, self.threat_name, self.create_uid.login
        )

        # Send notification to security admins
        self._notify_security_admins()
```

### 2. File Type & Size Validation (Enhance `trn_dms`)

Extend `trn.dms.category` with validation rules:

```python
class SPPDMSCategory(models.Model):
    _inherit = "trn.dms.category"

    # File type restrictions
    allowed_extensions = fields.Char(
        help="Comma-separated list of allowed extensions (e.g., 'pdf,jpg,png'). "
             "Empty means all types allowed."
    )
    blocked_extensions = fields.Char(
        default="exe,dll,bat,cmd,ps1,sh,msi,com,scr,vbs,js",
        help="Comma-separated list of blocked extensions (applied before allowed list)"
    )
    allowed_mimetypes = fields.Char(
        help="Comma-separated MIME types (e.g., 'application/pdf,image/*')"
    )

    # Size limits
    max_file_size_mb = fields.Integer(
        default=50,
        help="Maximum file size in megabytes (0 = no limit)"
    )

    # Scan requirements
    require_av_scan = fields.Boolean(
        default=True,
        help="Require antivirus scan before file is accessible"
    )

    def validate_file(self, filename, mimetype, size_bytes):
        """
        Validate file against category rules.

        Raises:
            ValidationError: If file doesn't meet requirements
        """
        self.ensure_one()
        errors = []

        extension = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()

        # Check blocked extensions
        if self.blocked_extensions:
            blocked = [e.strip().lower() for e in self.blocked_extensions.split(",")]
            if extension in blocked:
                errors.append(
                    _("File type '.%s' is not allowed for security reasons.") % extension
                )

        # Check allowed extensions
        if self.allowed_extensions and not errors:
            allowed = [e.strip().lower() for e in self.allowed_extensions.split(",")]
            if extension not in allowed:
                errors.append(
                    _("File type '.%s' not allowed. Allowed types: %s")
                    % (extension, self.allowed_extensions)
                )

        # Check MIME type
        if self.allowed_mimetypes:
            allowed_mimes = [m.strip() for m in self.allowed_mimetypes.split(",")]
            if not self._match_mimetype(mimetype, allowed_mimes):
                errors.append(
                    _("File content type '%s' not allowed.") % mimetype
                )

        # Check size
        if self.max_file_size_mb and size_bytes > (self.max_file_size_mb * 1024 * 1024):
            errors.append(
                _("File size exceeds limit of %s MB.") % self.max_file_size_mb
            )

        if errors:
            raise ValidationError("\n".join(errors))

        return True

    def _match_mimetype(self, mimetype, patterns):
        """Check if mimetype matches any pattern (supports wildcards like 'image/*')."""
        for pattern in patterns:
            if pattern == mimetype:
                return True
            if pattern.endswith("/*"):
                prefix = pattern[:-1]  # 'image/*' -> 'image/'
                if mimetype.startswith(prefix):
                    return True
        return False
```

### 3. Download Audit (Extend `trn_audit`)

Add download/access logging using existing `trn_audit` infrastructure:

```python
# In trn_audit module - extend rule model
class SppAuditRule(models.Model):
    _inherit = "trn.audit.rule"

    # New action flags for file operations
    is_log_download = fields.Boolean(
        "Log File Downloads",
        default=False,
        help="Log when files are downloaded"
    )
    is_log_preview = fields.Boolean(
        "Log File Previews",
        default=False,
        help="Log when files are previewed"
    )

# In trn_dms module - extend file model
class SPPDMSFile(models.Model):
    _inherit = "trn.dms.file"

    download_count = fields.Integer(default=0, readonly=True)
    last_download_date = fields.Datetime(readonly=True)
    last_download_user_id = fields.Many2one("res.users", readonly=True)

    def action_download(self):
        """Download file with audit logging."""
        self.ensure_one()

        # Atomic increment of download_count to prevent race conditions
        self.env.cr.execute("""
            UPDATE trn_dms_file
            SET download_count = download_count + 1,
                last_download_date = %s,
                last_download_user_id = %s
            WHERE id = %s
        """, (fields.Datetime.now(), self.env.uid, self.id))
        self.invalidate_recordset(["download_count", "last_download_date", "last_download_user_id"])

        # Log via trn_audit
        self.env["trn.audit.rule"].log_lifecycle_action(
            model_name=self._name,
            record_id=self.id,
            action="download",
            old_values={},
            new_values={
                "downloaded_by": self.env.user.login,
                "download_count": self.download_count,
            }
        )

        # Return download action
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.id}?download=true",
            "target": "self",
        }
```

### 4. Pluggable Storage Backend (`trn_storage_backend`)

Create an LGPL-licensed storage abstraction layer:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Storage Backend Architecture                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     trn.storage.backend                           │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │ Interface Methods:                                          │ │   │
│  │  │   store(binary, path) → reference                           │ │   │
│  │  │   retrieve(reference) → binary                              │ │   │
│  │  │   delete(reference) → bool                                  │ │   │
│  │  │   exists(reference) → bool                                  │ │   │
│  │  │   get_url(reference, expires) → url                         │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│       │                                                                  │
│       ├────────────────┬────────────────┬────────────────┐              │
│       ▼                ▼                ▼                ▼              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  Odoo    │    │   S3     │    │  Azure   │    │  MinIO   │          │
│  │  Default │    │          │    │  Blob    │    │          │          │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Backend Model

```python
class StorageBackend(models.Model):
    _name = "trn.storage.backend"
    _description = "Storage Backend Configuration"

    name = fields.Char(required=True)
    backend_type = fields.Selection([
        ("odoo", "Odoo Default (Filesystem/Database)"),
        ("s3", "Amazon S3 / S3-Compatible"),
        ("azure", "Azure Blob Storage"),
        ("minio", "MinIO"),
        ("filesystem", "External Filesystem"),
    ], required=True, default="odoo")
    is_default = fields.Boolean(default=False)
    is_active = fields.Boolean(default=True)

    # S3 / MinIO settings
    s3_endpoint_url = fields.Char(help="Custom endpoint for S3-compatible storage")
    s3_bucket = fields.Char()
    s3_access_key = fields.Char()
    s3_secret_key = fields.Char()
    s3_region = fields.Char(default="us-east-1")
    s3_use_ssl = fields.Boolean(default=True)

    # Azure settings
    azure_connection_string = fields.Char()
    azure_container = fields.Char()

    # Filesystem settings
    filesystem_path = fields.Char(help="Absolute path to storage directory")

    # Encryption
    encrypt_at_rest = fields.Boolean(
        default=False,
        help="Encrypt files before storing (uses trn_pii_encryption)"
    )

    _sql_constraints = [
        ("unique_default", "EXCLUDE (is_default WITH =) WHERE (is_default = true)",
         "Only one default storage backend allowed")
    ]

    @api.model
    def get_default_backend(self):
        """Get the default storage backend."""
        backend = self.search([("is_default", "=", True), ("is_active", "=", True)], limit=1)
        if not backend:
            # Fall back to Odoo default
            backend = self.search([("backend_type", "=", "odoo")], limit=1)
            if not backend:
                backend = self.create({
                    "name": "Odoo Default",
                    "backend_type": "odoo",
                    "is_default": True,
                })
        return backend

    def store(self, binary_data, path):
        """
        Store binary data and return a reference.

        Args:
            binary_data: bytes to store
            path: logical path/filename

        Returns:
            str: reference to retrieve the file later
        """
        self.ensure_one()
        method = getattr(self, f"_store_{self.backend_type}", None)
        if not method:
            raise NotImplementedError(f"Storage backend {self.backend_type} not implemented")

        if self.encrypt_at_rest:
            binary_data = self._encrypt_data(binary_data, path)

        return method(binary_data, path)

    def retrieve(self, reference):
        """
        Retrieve binary data by reference.

        Args:
            reference: storage reference from store()

        Returns:
            bytes: the file content
        """
        self.ensure_one()
        method = getattr(self, f"_retrieve_{self.backend_type}", None)
        if not method:
            raise NotImplementedError(f"Storage backend {self.backend_type} not implemented")

        data = method(reference)

        if self.encrypt_at_rest:
            data = self._decrypt_data(data, reference)

        return data

    def delete(self, reference):
        """Delete file by reference."""
        self.ensure_one()
        method = getattr(self, f"_delete_{self.backend_type}", None)
        if method:
            return method(reference)
        return False

    def get_public_url(self, reference, expires_in=3600):
        """
        Get a time-limited public URL for the file.

        Args:
            reference: storage reference
            expires_in: seconds until URL expires

        Returns:
            str: presigned URL or None if not supported
        """
        self.ensure_one()
        method = getattr(self, f"_get_url_{self.backend_type}", None)
        if method:
            return method(reference, expires_in)
        return None

    # S3 Implementation
    def _get_s3_client(self):
        import boto3

        session_kwargs = {}
        if self.s3_access_key and self.s3_secret_key:
            session_kwargs["aws_access_key_id"] = self.s3_access_key
            session_kwargs["aws_secret_access_key"] = self.s3_secret_key

        client_kwargs = {"region_name": self.s3_region}
        if self.s3_endpoint_url:
            client_kwargs["endpoint_url"] = self.s3_endpoint_url
        client_kwargs["use_ssl"] = self.s3_use_ssl

        return boto3.client("s3", **session_kwargs, **client_kwargs)

    def _store_s3(self, binary_data, path):
        import uuid

        client = self._get_s3_client()
        key = f"{path}/{uuid.uuid4().hex}"

        client.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=binary_data,
        )

        return f"s3://{self.s3_bucket}/{key}"

    def _retrieve_s3(self, reference):
        client = self._get_s3_client()

        # Parse reference: s3://bucket/key
        parts = reference.replace("s3://", "").split("/", 1)
        bucket, key = parts[0], parts[1]

        response = client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def _get_url_s3(self, reference, expires_in):
        client = self._get_s3_client()

        parts = reference.replace("s3://", "").split("/", 1)
        bucket, key = parts[0], parts[1]

        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    # Azure Implementation
    def _store_azure(self, binary_data, path):
        from azure.storage.blob import BlobServiceClient
        import uuid

        blob_service = BlobServiceClient.from_connection_string(self.azure_connection_string)
        container_client = blob_service.get_container_client(self.azure_container)

        blob_name = f"{path}/{uuid.uuid4().hex}"
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(binary_data)

        return f"azure://{self.azure_container}/{blob_name}"

    def _retrieve_azure(self, reference):
        from azure.storage.blob import BlobServiceClient

        parts = reference.replace("azure://", "").split("/", 1)
        container, blob_name = parts[0], parts[1]

        blob_service = BlobServiceClient.from_connection_string(self.azure_connection_string)
        blob_client = blob_service.get_blob_client(container, blob_name)

        return blob_client.download_blob().readall()
```

### 5. Document Versioning (Native in `trn_dms`)

Document versioning is implemented directly in `trn_dms` as a native feature:

```python
class SPPDMSFileVersion(models.Model):
    _name = "trn.dms.file.version"
    _description = "DMS File Version"
    _order = "version_number desc"

    file_id = fields.Many2one(
        "trn.dms.file",
        required=True,
        ondelete="cascade",
        index=True,
    )
    version_number = fields.Integer(required=True)
    content = fields.Binary(attachment=True, required=True)
    checksum = fields.Char(readonly=True)
    size = fields.Float(readonly=True)

    created_by_id = fields.Many2one("res.users", default=lambda self: self.env.uid)
    created_date = fields.Datetime(default=fields.Datetime.now)
    comment = fields.Text(help="Description of changes in this version")

    is_current = fields.Boolean(default=True, index=True)

    _sql_constraints = [
        ("unique_version", "UNIQUE(file_id, version_number)",
         "Version number must be unique per file"),
    ]


class SPPDMSFile(models.Model):
    _inherit = "trn.dms.file"

    version_ids = fields.One2many("trn.dms.file.version", "file_id", "Versions")
    current_version = fields.Integer(compute="_compute_current_version", store=True)
    is_versioned = fields.Boolean(default=False)

    @api.depends("version_ids", "version_ids.is_current")
    def _compute_current_version(self):
        for record in self:
            current = record.version_ids.filtered("is_current")
            record.current_version = current.version_number if current else 0

    def _inverse_content(self):
        """Override to create version on content change."""
        for record in self:
            if record.is_versioned and record.version_ids:
                # Create new version
                record._create_new_version()
            else:
                super(SPPDMSFile, record)._inverse_content()

    def _create_new_version(self, comment=None):
        """Create a new version of the file."""
        self.ensure_one()

        # Mark current version as not current
        self.version_ids.filtered("is_current").write({"is_current": False})

        # Create new version
        new_version_num = max(self.version_ids.mapped("version_number") or [0]) + 1

        self.env["trn.dms.file.version"].create({
            "file_id": self.id,
            "version_number": new_version_num,
            "content": self.content,
            "checksum": self.checksum,
            "size": self.size,
            "comment": comment,
            "is_current": True,
        })

    def action_restore_version(self, version_id):
        """Restore a previous version."""
        version = self.env["trn.dms.file.version"].browse(version_id)
        if version.file_id != self:
            raise UserError(_("Version does not belong to this file"))

        # This will trigger _create_new_version via inverse
        self.content = version.content
```

### 6. Enhanced Preview (`trn_dms_preview`)

Separate module for enhanced document preview:

```javascript
/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";

export class DocumentPreviewWidget extends Component {
    static template = "trn_dms_preview.DocumentPreview";
    static props = {
        record: Object,
        name: String,
    };

    setup() {
        this.state = useState({
            loading: false,
            previewUrl: null,
            error: null,
        });
    }

    get mimetype() {
        return this.props.record.data.mimetype;
    }

    get isPdf() {
        return this.mimetype === "application/pdf";
    }

    get isImage() {
        return this.mimetype?.startsWith("image/");
    }

    get isPreviewable() {
        return this.isPdf || this.isImage;
    }

    async openPreview() {
        if (this.isPdf) {
            // Use PDF.js viewer
            const url = `/trn_dms_preview/pdf/${this.props.record.resId}`;
            window.open(url, "_blank", "width=900,height=700");
        } else if (this.isImage) {
            // Use image lightbox
            this.state.previewUrl = `/web/image/${this.props.record.resId}`;
            this.state.showLightbox = true;
        }
    }
}

registry.category("view_widgets").add("document_preview", DocumentPreviewWidget);
```

## Module Structure

```
New Modules:
├── trn_attachment_av_scan/        # System-wide AV scanning
│   ├── models/
│   │   ├── av_scanner_backend.py
│   │   └── ir_attachment.py
│   ├── data/
│   │   └── av_scanner_data.xml
│   ├── security/
│   │   ├── security.xml
│   │   └── ir.model.access.csv
│   └── views/
│       ├── av_scanner_backend_views.xml
│       └── ir_attachment_views.xml
│
├── trn_storage_backend/           # Pluggable storage (LGPL)
│   ├── models/
│   │   └── storage_backend.py     # S3, Azure, filesystem implementations
│   ├── data/
│   │   └── storage_backend_data.xml
│   ├── security/
│   │   ├── privileges.xml
│   │   ├── groups.xml
│   │   └── ir.model.access.csv
│   └── views/
│       └── storage_backend_views.xml
│
└── trn_dms_preview/               # Enhanced preview (future)
    ├── controllers/
    │   └── preview.py
    └── static/src/
        ├── js/
        └── xml/

Enhanced Existing Modules:
├── trn_dms/                       # File validation + versioning
│   ├── models/
│   │   ├── dms_category.py        # File type/size validation rules
│   │   ├── dms_file.py            # Versioning fields & methods
│   │   └── dms_file_version.py    # Version history model
│   ├── views/
│   │   ├── dms_category_views.xml # Validation config UI
│   │   └── dms_file_version_views.xml
│   └── wizard/
│       └── restore_version_wizard.py
│
└── trn_audit/
    └── models/trn_audit_rule.py   # is_log_download/preview/export flags
```

## Dependency Graph

```
                    ┌─────────────────────┐
                    │     queue_job       │
                    └─────────────────────┘
                              ▲
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ trn_attachment_av_scan  │     │   trn_storage_backend   │
└─────────────────────────┘     └─────────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────┐
                              │         trn_dms             │
                              │  (validation + versioning)  │
                              └─────────────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────┐
                              │      trn_dms_preview        │
                              │         (future)            │
                              └─────────────────────────────┘
```

## Implementation Plan

| Phase | Module | Status | Priority | Notes |
|-------|--------|--------|----------|-------|
| 1a | `trn_dms` file validation | ✅ Done | P0 | Category-level validation |
| 1b | `trn_dms` versioning | ✅ Done | P0 | Native feature |
| 1c | `trn_attachment_av_scan` | ✅ Done | P0 | System-wide AV |
| 2a | `trn_audit` download flags | ✅ Done | P1 | New action flags |
| 2b | `trn_storage_backend` | ✅ Done | P1 | S3/Azure/FS backends |
| 3 | `trn_dms_preview` | ❌ Pending | P2 | Future enhancement |
| 4 | Drag-and-drop upload | ❌ Pending | P3 | Future enhancement |

## Configuration Examples

### ClamAV Setup

```ini
# odoo.conf
[av_scan]
enabled = true
backend = clamd_socket
clamd_socket = /var/run/clamav/clamd.sock
max_file_size_mb = 100
scan_timeout = 60
```

### S3 Storage

```ini
# odoo.conf
[storage]
backend = s3
s3_bucket = myproject-documents
s3_region = eu-west-1
s3_endpoint_url = https://s3.eu-west-1.amazonaws.com
# Credentials via IAM role or environment variables
```

### MinIO Storage (On-Premise S3-Compatible)

```ini
# odoo.conf
[storage]
backend = s3
s3_bucket = myproject-documents
s3_endpoint_url = http://minio.internal:9000
s3_access_key = minioadmin
s3_secret_key = minioadmin
s3_use_ssl = false
```

## Consequences

### Positive

1. **Defense in depth**: Malware scanning protects entire Odoo instance
2. **Cloud-ready**: S3/Azure storage enables scalable deployments
3. **Compliance**: Audit trails for document access
4. **Flexibility**: Configurable validation per document category
5. **LGPL licensed**: No OCA dependency issues

### Negative

1. **Operational overhead**: ClamAV daemon requires maintenance
2. **Latency**: Async scanning means files aren't immediately verified
3. **Complexity**: Multiple modules to configure
4. **Cloud costs**: External storage incurs egress/API costs

### Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| ClamAV daemon unavailable | Medium | Medium | Graceful fallback to "skipped" status |
| False positives | Low | Medium | Admin review queue, whitelist capability |
| Storage backend failure | Low | High | Retry logic, fallback to local storage |
| Large file scan timeout | Medium | Low | Size limits, skip option |

## Security Considerations

1. **AV Signatures**: Keep ClamAV signatures updated (freshclam)
2. **Quarantine Access**: Restrict quarantine directory permissions
3. **Storage Credentials**: Use IAM roles over static keys where possible
4. **Audit Log Protection**: Prevent deletion of audit logs
5. **Size Limits**: Enforce at both category and system level

## Testing Requirements

1. **AV Scan Tests**:
   - Mock ClamAV responses
   - Test quarantine flow
   - Test async job processing

2. **Storage Backend Tests**:
   - Test each backend type with mocked clients
   - Test fallback behavior
   - Test presigned URL generation

3. **Validation Tests**:
   - Test extension whitelist/blacklist
   - Test MIME type matching with wildcards
   - Test size limit enforcement

## Related ADRs

- ADR-012: PII Encryption Strategy (encryption at rest option)
- ADR-004: Access Rights Management (audit logging)
- ADR-011: Data Classification System (file sensitivity)

## References

- [ClamAV Documentation](https://docs.clamav.net/)
- [pyclamd Library](https://xael.org/pages/pyclamd-en.html)
- [Boto3 S3 Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- [Azure Blob Storage Python SDK](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-python)
