"""Alert emails and link pages, in the language the alert was created in."""

from html import escape

from tarameteo.alerts import Alert

UNITS = {"temperature": "°C", "humidity": "%", "pressure": "hPa", "rain": "mm", "snow": "mm"}

TEXT = {
    "en": {
        "colon": ":",
        "fields": {"temperature": "temperature", "humidity": "humidity", "pressure": "pressure", "rain": "rain", "snow": "snow"},
        "conditions": {"above": "above", "below": "below"},
        "confirm_subject": "Confirm your weather alert",
        "confirm_body": "Someone asked for this alert to be sent to this address:\n\n{rule}\n\nTo start it, open this link and press Confirm:\n{url}\n\nOtherwise, ignore this email; nothing will be sent.\n",
        "alert_subject": "{sensor}: {field} is {value}",
        "alert_body": "{sensor}: {field} is {value}.\n\nYour alert: {rule}\nYou'll get one more email when it's back to normal.\n\nTo stop this alert:\n{url}\n",
        "normal_subject": "{sensor}: {field} back to normal ({value})",
        "normal_body": "{sensor}: {field} is back to {value}.\n\nYour alert: {rule}\n\nTo stop this alert:\n{url}\n",
        "confirm_title": "Confirm this alert?",
        "confirm_button": "Confirm",
        "confirmed": "Alert confirmed: {rule}. You'll get an email when it happens, and another when it's back to normal.",
        "remove_title": "Stop this alert?",
        "remove_button": "Stop alert",
        "removed": "Alert stopped. You won't get any more emails for it.",
    },
    "fr": {
        "colon": " :",
        "fields": {"temperature": "température", "humidity": "humidité", "pressure": "pression", "rain": "pluie", "snow": "neige"},
        "conditions": {"above": "au-dessus de", "below": "en dessous de"},
        "confirm_subject": "Confirmez votre alerte météo",
        "confirm_body": "Quelqu'un a demandé que cette alerte soit envoyée à cette adresse :\n\n{rule}\n\nPour l'activer, ouvrez ce lien et appuyez sur Confirmer :\n{url}\n\nSinon, ignorez ce courriel ; rien ne sera envoyé.\n",
        "alert_subject": "{sensor} : {field} à {value}",
        "alert_body": "{sensor} : {field} à {value}.\n\nVotre alerte : {rule}\nVous recevrez un dernier courriel au retour à la normale.\n\nPour arrêter cette alerte :\n{url}\n",
        "normal_subject": "{sensor} : {field} revenue à la normale ({value})",
        "normal_body": "{sensor} : {field} revenue à {value}.\n\nVotre alerte : {rule}\n\nPour arrêter cette alerte :\n{url}\n",
        "confirm_title": "Confirmer cette alerte ?",
        "confirm_button": "Confirmer",
        "confirmed": "Alerte confirmée : {rule}. Vous recevrez un courriel quand cela arrivera, et un autre au retour à la normale.",
        "remove_title": "Arrêter cette alerte ?",
        "remove_button": "Arrêter l'alerte",
        "removed": "Alerte arrêtée. Vous ne recevrez plus de courriels pour celle-ci.",
    },
}

# No alert to take the language from, so say it both ways.
INVALID = "Ce lien est invalide ou expiré. / This link is invalid or expired."
GONE = "Cette alerte n'existe plus. / This alert no longer exists."


def value(alert: Alert, x: float) -> str:
    number = f"{x:g}" if alert.language == "en" else f"{x:g}".replace(".", ",")
    return f"{number} {UNITS[alert.field]}"


def rule(alert: Alert) -> str:
    """'outdoor: temperature below -20 °C'."""
    text = TEXT[alert.language]
    field, condition = text["fields"][alert.field], text["conditions"][alert.condition]
    return f"{alert.sensor}{text['colon']} {field} {condition} {value(alert, alert.threshold)}"


def email(alert: Alert, key: str, url: str, reading: float | None = None) -> tuple[str, str]:
    """Subject and body for confirm, alert or normal."""
    text = TEXT[alert.language]
    args = {
        "sensor": alert.sensor,
        "field": text["fields"][alert.field],
        "value": value(alert, reading) if reading is not None else "",
        "rule": rule(alert),
        "url": url,
    }
    return text[f"{key}_subject"].format(**args), text[f"{key}_body"].format(**args)


def page(language: str, *paragraphs: str, button: str | None = None) -> str:
    """A bare page; with a button, it posts back to its own URL, which link scanners don't do."""
    text = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    form = f'<form method="post"><button type="submit">{escape(button)}</button></form>' if button else ""
    return (
        f'<!doctype html><html lang="{language}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>TaraMeteo</title>'
        '<body style="font-family: sans-serif; max-width: 32rem; margin: 3rem auto; padding: 0 1rem">'
        f"{text}{form}</body></html>"
    )
