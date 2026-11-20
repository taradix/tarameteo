import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def render(env, path, template_vars):
    template = env.get_template(f"{path.name}.j2")
    path.write_text(template.render(template_vars))

def prepare_template_vars(environ):
    additional_server_names = environ.get("ADDITIONAL_SERVER_NAMES", "")

    return {
        "TRUSTED_NETWORK": environ.get("TRUSTED_NETWORK", ""),
        "SERVER_HOSTNAME": environ.get("SERVER_HOSTNAME", ""),
        "ADDITIONAL_SERVER_NAMES": [item.strip() for item in additional_server_names.split(",") if item.strip()],
    }

def main():
    env = Environment(loader=FileSystemLoader("/etc/nginx/conf.d/templates"))

    print("Render config")
    template_vars = prepare_template_vars(os.environ)
    render(env, Path("/etc/nginx/includes/sites-default.conf"), template_vars)
    render(env, Path("/etc/nginx/nginx.conf"), template_vars)


if __name__ == "__main__":
    main()
