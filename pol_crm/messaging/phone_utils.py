"""
Phone Normalization and Validation Utilities for Iran
Handles Persian/Arabic digits, prefixes, and E.164 conversion.
"""

import re

PERSIAN_TO_ENGLISH = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_iranian_mobile(raw_phone):
    """
    Normalizes an Iranian mobile phone number.
    Returns a tuple: (canonical_e164, local_format, is_valid)
    Examples:
      '09121234567' -> ('+989121234567', '09121234567', True)
      '+98 912 123 4567' -> ('+989121234567', '09121234567', True)
    """
    if not raw_phone:
        return None, None, False

    # Convert Persian/Arabic digits and remove spaces/dashes
    cleaned = str(raw_phone).translate(PERSIAN_TO_ENGLISH)
    digits = re.sub(r"\D", "", cleaned)

    # Match patterns:
    # 00989xxxxxxxxx (14 digits)
    if digits.startswith("00989") and len(digits) == 14:
        digits = digits[4:]
    # 989xxxxxxxxx (12 digits)
    elif digits.startswith("989") and len(digits) == 12:
        digits = digits[2:]
    # 09xxxxxxxxx (11 digits)
    elif digits.startswith("09") and len(digits) == 11:
        digits = digits[1:]
    # 9xxxxxxxxx (10 digits)
    elif digits.startswith("9") and len(digits) == 10:
        pass
    else:
        # Invalid format
        return None, None, False

    # Verify 10-digit mobile number starting with 9
    if len(digits) == 10 and digits.startswith("9"):
        e164 = f"+98{digits}"
        local = f"0{digits}"
        return e164, local, True

    return None, None, False
