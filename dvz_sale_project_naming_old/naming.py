"""Pure naming helpers. No Odoo imports, no database access, no sequence allocation."""
import re

SHORT_CODE_RE = re.compile(r'[A-Z0-9]{1,16}')
REFERENCE_RE = re.compile(r'[A-Z0-9]+(?:[._/-][A-Z0-9]+)*')


def normalize(value):
    """Trim and uppercase text; preserve leading zeroes in text references."""
    if value is None or value is False:
        return ''
    if not isinstance(value, str):
        raise ValueError('Enter codes as text, not numbers or other objects.')
    return value.strip().upper()


def short_code(value, label, required=True):
    value = normalize(value)
    if not value and not required:
        return ''
    # if not SHORT_CODE_RE.fullmatch(value):
    #     raise ValueError(f'{label} must contain 1 to 16 English letters or digits, without spaces.')
    return value


def reference(value, label='Project reference', required=True):
    value = normalize(value)
    if not value and not required:
        return ''
    if len(value) > 40 or not REFERENCE_RE.fullmatch(value):
        raise ValueError(
            f'{label} must contain 1 to 40 English letters/digits; '
            'single hyphens, dots, underscores or slashes may separate groups.'
        )
    return value


def make_project_code(salesperson, division, project_reference, suffix=''):
    parts = [
        short_code(salesperson, 'Salesperson abbreviation'),
        short_code(division, 'Division code'),
        reference(project_reference),
    ]
    suffix = short_code(suffix, 'Project suffix', required=False)
    if suffix:
        parts.append(suffix)
    return '-'.join(parts)


def make_project_name(order_number, code, include_so=True):
    if not code:
        return ''
    if not include_so:
        return code
    if not isinstance(order_number, str) or not order_number.strip():
        raise ValueError('A sales order number is required for the project name.')
    return f'{order_number.strip()} || {code}'
