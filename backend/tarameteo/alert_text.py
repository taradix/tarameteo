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
        "alert_body": "{sensor}: {field} is {value}.\n\nYour alert: {rule}\nYou'll get one more email when it's back to normal.\n\nTo stop this alert:\n{url}\n\nAll your alerts:\n{manage_url}\n",
        "normal_subject": "{sensor}: {field} back to normal ({value})",
        "normal_body": "{sensor}: {field} is back to {value}.\n\nYour alert: {rule}\n\nTo stop this alert:\n{url}\n\nAll your alerts:\n{manage_url}\n",
        "manage_subject": "Your weather alerts",
        "manage_body": "To see and stop the weather alerts sent to this address, open this link within an hour:\n{url}\n\nIf you didn't ask for this, ignore this email.\n",
        "manage_title": "Alerts sent to {email}",
        "manage_empty": "No alerts are sent to this address.",
        "manage_stop_all": "Stop all alerts",
        "pending": "(not confirmed)",
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
        "alert_body": "{sensor} : {field} à {value}.\n\nVotre alerte : {rule}\nVous recevrez un dernier courriel au retour à la normale.\n\nPour arrêter cette alerte :\n{url}\n\nToutes vos alertes :\n{manage_url}\n",
        "normal_subject": "{sensor} : {field} revenue à la normale ({value})",
        "normal_body": "{sensor} : {field} revenue à {value}.\n\nVotre alerte : {rule}\n\nPour arrêter cette alerte :\n{url}\n\nToutes vos alertes :\n{manage_url}\n",
        "manage_subject": "Vos alertes météo",
        "manage_body": "Pour voir et arrêter les alertes météo envoyées à cette adresse, ouvrez ce lien d'ici une heure :\n{url}\n\nSi vous n'avez rien demandé, ignorez ce courriel.\n",
        "manage_title": "Alertes envoyées à {email}",
        "manage_empty": "Aucune alerte n'est envoyée à cette adresse.",
        "manage_stop_all": "Arrêter toutes les alertes",
        "pending": "(non confirmée)",
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


def value(alert: Alert, x: float, language: str | None = None) -> str:
    number = f"{x:g}" if (language or alert.language) == "en" else f"{x:g}".replace(".", ",")
    return f"{number} {UNITS[alert.field]}"


def rule(alert: Alert, language: str | None = None) -> str:
    """'outdoor: temperature below -20 °C', in the alert's language unless given another."""
    language = language or alert.language
    text = TEXT[language]
    field, condition = text["fields"][alert.field], text["conditions"][alert.condition]
    return f"{alert.sensor}{text['colon']} {field} {condition} {value(alert, alert.threshold, language)}"


def email(alert: Alert, key: str, url: str, reading: float | None = None, manage_url: str = "") -> tuple[str, str]:
    """Subject and body for confirm, alert or normal."""
    text = TEXT[alert.language]
    args = {
        "sensor": alert.sensor,
        "field": text["fields"][alert.field],
        "value": value(alert, reading) if reading is not None else "",
        "rule": rule(alert),
        "url": url,
        "manage_url": manage_url,
    }
    return text[f"{key}_subject"].format(**args), text[f"{key}_body"].format(**args)


def _document(language: str, body: str) -> str:
    return (
        f'<!doctype html><html lang="{language}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1"><title>TaraMeteo</title>'
        '<body style="font-family: sans-serif; max-width: 32rem; margin: 3rem auto; padding: 0 1rem">'
        f"{body}</body></html>"
    )


def _button(label: str, action: str = "") -> str:
    """Posts to action (default: this page's URL), which link scanners don't do."""
    target = f' action="{escape(action)}"' if action else ""
    return f'<form method="post"{target}><button type="submit">{escape(label)}</button></form>'


def page(language: str, *paragraphs: str, button: str | None = None) -> str:
    """A bare page; with a button, it posts back to its own URL."""
    text = "".join(f"<p>{escape(p)}</p>" for p in paragraphs)
    return _document(language, text + (_button(button) if button else ""))


def manage_page(language: str, email: str, alerts: list[Alert]) -> str:
    """The address's alerts, each with a stop button, and one to stop them all."""
    text = TEXT[language]
    title = f"<h1 style=\"font-size: 1.25rem\">{escape(text['manage_title'].format(email=email))}</h1>"
    if not alerts:
        return _document(language, f"{title}<p>{escape(text['manage_empty'])}</p>")
    items = "".join(
        f"<li>{escape(rule(a, language))}{'' if a.confirmed else ' ' + escape(text['pending'])}"
        f"{_button(text['remove_button'], f'?alert={a.id}')}</li>"
        for a in alerts
    )
    return _document(language, f"{title}<ul>{items}</ul>{_button(text['manage_stop_all'])}")
