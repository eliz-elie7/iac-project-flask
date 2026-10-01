import re

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
MIN_PASSWORD_LENGTH = 8
MAX_DURATION_HOURS = 72


class ValidationError(Exception):
    pass


def validate_username(username: str) -> str:
    username = (username or '').strip()
    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Le nom d'utilisateur doit contenir entre 3 et 32 caractères "
            "(lettres, chiffres, tirets, underscores uniquement)."
        )
    return username


def validate_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
    return password


def validate_duration_hours(raw_value: str) -> int:
    try:
        hours = int(raw_value)
    except (TypeError, ValueError):
        raise ValidationError("Durée invalide.")
    if not (1 <= hours <= MAX_DURATION_HOURS):
        raise ValidationError(f"La durée doit être comprise entre 1 et {MAX_DURATION_HOURS} heures.")
    return hours