# Error Handling & Logging Principles

Standards for exceptions, user messages, and logging in Training Sample.

## Core Principles

1. **User vs. Technical** - User-facing errors are clear and actionable; technical errors are logged for debugging
2. **Fail Fast** - Validate early, reject invalid data before processing
3. **No PII in Logs** - Never log personally identifiable information
4. **Structured Logging** - Use consistent log levels and formats

## Exception Hierarchy

Use Odoo's built-in exceptions appropriately:

| Exception | When to Use | User Sees |
|-----------|-------------|-----------|
| `ValidationError` | Invalid data, constraint violations | Error dialog |
| `UserError` | Business rule violations, user mistakes | Error dialog |
| `AccessError` | Permission denied | Access denied page |
| `MissingError` | Record not found | Error dialog |
| `RedirectWarning` | Error with action button | Dialog with action |

## Exception Patterns

### ValidationError - Data Validation

```python
from odoo.exceptions import ValidationError

@api.constrains('birth_date')
def _check_birth_date(self):
    for record in self:
        if record.birth_date and record.birth_date > fields.Date.today():
            raise ValidationError(_("Birth date cannot be in the future."))
```

### UserError - Business Rules

```python
from odoo.exceptions import UserError

def action_approve(self):
    if self.state != 'pending':
        raise UserError(_("Only pending requests can be approved."))
    if not self.env.user.has_group('trn_security.group_validator'):
        raise UserError(_("You don't have permission to approve requests."))
```

### Error Messages

Write error messages that are actionable:

```python
# Bad: Just states the problem
raise UserError(_("Cannot modify active variable."))

# Good: States problem + explains why + provides solution
raise UserError(_(
    "Cannot modify '%(name)s' while it is Active.\n\n"
    "Active variables are locked to ensure data consistency.\n"
    "To edit: Click 'Deactivate' first, make your changes, then 'Reactivate'.",
    name=record.name,
))
```

**Error message structure:**
1. **What happened** - Clear statement of the issue
2. **Why** - Brief explanation (optional but helpful)
3. **How to fix** - Concrete steps the user can take

```python
# Good - actionable, specific
raise UserError(_(
    "Cannot submit: Order %(name)s already has an active workflow.",
    name=record.name,
))

# Bad - vague, unhelpful
raise UserError(_("Error occurred."))

# Good - includes resolution
raise ValidationError(_(
    "Phone number format is invalid. "
    "Please use format: +1-XXX-XXX-XXXX"
))
```

## Audit Trail vs Operational Logging

| Tool | Purpose | Storage | Use For |
|------|---------|---------|---------|
| **trn_audit** | Compliance audit trail | Database (permanent) | Business events, state changes, approvals |
| **_logger** | Operational debugging | Log files (ephemeral) | Errors, exceptions, performance issues |

**Rule of thumb:** If auditors or supervisors need to see it, use `trn_audit`. If only developers need it for troubleshooting, use `_logger`.

## Logging Standards

### Setup

```python
import logging

_logger = logging.getLogger(__name__)
```

### Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| `DEBUG` | Development troubleshooting | `_logger.debug("Processing record %s", record.id)` |
| `INFO` | Normal operations, milestones | `_logger.info("Batch complete: %d records", count)` |
| `WARNING` | Recoverable issues | `_logger.warning("Retry %d for API call", attempt)` |
| `ERROR` | Failures requiring attention | `_logger.error("Payment failed: %s", error)` |
| `CRITICAL` | System-level failures | `_logger.critical("Database connection lost")` |

### Logging Patterns

```python
# Use lazy formatting (not f-strings)
_logger.info("Processing %d records for program %s", len(records), program.name)

# Include context
_logger.error(
    "Order creation failed for partner_id=%s, order_id=%s: %s",
    partner.id, order.id, str(e)
)

# Log exceptions with traceback
try:
    self._process_payment()
except Exception as e:
    _logger.exception("Payment processing failed")  # Includes traceback
    raise UserError(_("Payment failed. Please try again."))
```

## PII Protection

### Never Log

- National IDs, SSN, tax IDs
- Full names with identifiers
- Biometric data
- Bank account numbers
- Phone numbers, addresses

### Safe Logging

```python
# Bad - logs PII
_logger.info("Processing %s, ID: %s", partner.name, partner.national_id)

# Good - use internal IDs only
_logger.info("Processing partner_id=%s", partner.id)

# Good - mask sensitive data
_logger.info("Processing ID ending in %s", national_id[-4:] if national_id else "N/A")
```

## Error Recovery

### Graceful Degradation

```python
def get_external_data(self):
    try:
        return self._call_external_api()
    except ConnectionError:
        _logger.warning("External API unavailable, using cached data")
        return self._get_cached_data()
```

### Retry Pattern

```python
import time

MAX_RETRIES = 3

def call_with_retry(self, func):
    for attempt in range(MAX_RETRIES):
        try:
            return func()
        except ConnectionError as e:
            if attempt == MAX_RETRIES - 1:
                _logger.error("All retries exhausted: %s", e)
                raise
            wait = 2 ** attempt  # Exponential backoff
            _logger.warning("Retry %d in %ds", attempt + 1, wait)
            time.sleep(wait)
```

## API Error Responses

For REST APIs, return structured errors:

```python
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request data",
        "details": [
            {"field": "birth_date", "message": "Must be in the past"}
        ]
    }
}
```

---

**See also:** [Testing](testing.md), [API Design](api-design.md)
