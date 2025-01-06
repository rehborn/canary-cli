#!/usr/bin/env python3
import configparser
import os
import sys
import time
import tomllib
import typing
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import humanize
import questionary
import requests
import typer
import yaml
from dotenv import dotenv_values
from rich import print
from rich.box import SIMPLE_HEAD as TABLE_STYLE
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from typing_extensions import Annotated, Literal

CONFIG_DIR = Path.home() / '.config/ccd/'

DEFAULT_CONFIG = {
    'API_URL': 'http://localhost:8001',
    'API_KEY': 'root',
}


class Config:
    def __init__(self, config_dir: Path, config_file: str = 'config.yaml'):
        self.config_path = config_dir / config_file
        self.config = {}
        if not config_dir.exists():
            os.makedirs(config_dir, exist_ok=True)
            self.config = DEFAULT_CONFIG
            self.dump()
        else:
            self.load()

    def load(self):
        with open(self.config_path, 'r') as config_stream:
            self.config = yaml.load(config_stream, Loader=yaml.FullLoader)

    def dump(self):
        with open(self.config_path, 'w') as config_stream:
            yaml.dump(self.config, config_stream)

    def __getitem__(self, item):
        return self.config[item]

    def __setitem__(self, key, value):
        self.config[key] = value
        self.dump()


class API:
    def __init__(self, api_url: str, api_key: str):
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.api_url = api_url

    def request(self, method: Literal['GET', 'POST', 'PUT', 'DELETE'], path: str, raw_data=None, data: dict = None,
                files=None):
        try:
            r = requests.request(method, '/'.join([self.api_url, path, '']), headers=self.headers, json=data,
                                 files=files, data=raw_data)
        except Exception as e:
            print(f"[bold red]Exception: {type(e).__name__}[/bold red]")
            sys.exit(1)
        if r.status_code >= 400:
            if r.json()["detail"]:
                if len(r.json()) > 1:
                    for e in r.json()["detail"]:
                        print(f"[bold red]{e['loc'][1]}: {e["msg"]}[/bold red]")
                else:
                    print(f"[red]{r.json()["detail"]}[/red]", )
            sys.exit(1)
        return r.json()

    def get(self, path) -> dict:
        return self.request('GET', path)

    def create(self, path, data) -> dict:
        return self.request('POST', path, data=data)

    def update(self, path, data) -> dict:
        return self.request('PUT', path, data=data)

    def delete(self, path) -> dict:
        return self.request('DELETE', path)

    def upload(self, path, file) -> dict:
        return self.request('POST', path, raw_data=file)
        # return self.request('POST', path, files={'file': files})


def time_since(iso_date: str) -> str:
    tz_unaware = datetime.fromisoformat(iso_date)
    tz_aware = tz_unaware.replace(tzinfo=timezone.utc)
    tz_local = datetime.now().astimezone()
    return humanize.naturaltime(tz_local - tz_aware)


def print_kv(items):
    table = Table(box=None, show_header=False)
    for key, value in reversed(items.items()):
        k = f'[cyan]{key.upper()}[/cyan]'
        if key == 'git_key':
            v = f'[green]{value['name']}[/green]' if value is not None else '[red]NO KEY ASSIGNED[/red]'
        elif key == 'token':
            v = f'[yellow]{value}[/yellow]'
        elif key == 'projects':
            v = ', '.join([p['name'] for p in value]) or '-'
        else:
            v = f'[white]{value}[/white]'
        table.add_row(k, v)
    console.print(table)


table_options = {
    'style': 'blue',
    'box': TABLE_STYLE,
    'expand': False
}

typer_options = {
    'no_args_is_help': True,
    # 'add_help_option': False,
    # 'rich_markup_mode': 'rich',
    'options_metavar': '',
    # 'subcommand_metavar': ''
}

cliconfig = Config(CONFIG_DIR)
api = API(cliconfig['API_URL'], cliconfig['API_KEY'])
app = typer.Typer(rich_markup_mode='rich', pretty_exceptions_enable=False, **typer_options)
# custom_theme = Theme({
#     "info": "dim cyan",
#     "warning": "magenta",
#     "danger": "bold red"
# })
# console = Console(theme=custom_theme)
console = Console()

# CLI Config
HELP_CONFIG = f"""
Configure CLI\n\n
[cyan]
ccd cli set API_KEY 
ccd cli set API_URL
[/cyan]
"""

cli_config_app = typer.Typer(**typer_options)
app.add_typer(cli_config_app, name="cli", help=HELP_CONFIG)


@cli_config_app.command('list', help='list cli config')
def cli_config_list():
    table = Table(**table_options)

    for column in ['Key', 'Value']:
        table.add_column(column)

    if len(cliconfig.config) > 0:
        for key, value in cliconfig.config.items():
            table.add_row(key, value)

    console.print(table)


def complete_files():
    return []


def complete_cli_config_keys():
    return DEFAULT_CONFIG.keys()


@cli_config_app.command('set', help='set cli config variable', **typer_options)
def cli_config_set(key: Annotated[str, typer.Argument(autocompletion=complete_cli_config_keys)], value: str):
    cliconfig[key] = value
    print(f"{key}={value}")


# Config
def complete_config_keys():
    return [
        'DISCORD_WEBHOOK',
    ]


config_app = typer.Typer(**typer_options)
app.add_typer(config_app, name="config", help='Manage Config')


@config_app.command('list', help='list config')
def config_list():
    result = api.get('config')
    print(result)
    table = Table(box=None, show_header=False)
    for c in result:
        k, v = c['key'], c['value']
        table.add_row(f'[cyan]{k}[/cyan]', f'{v}')
    console.print(table)


@config_app.command('set', help='set config')
def config_set(key: Annotated[str, typer.Argument(autocompletion=complete_config_keys)], value: str):
    print(api.update('config', {'key': key, 'value': value}))


@config_app.command('unset', help='unset config')
def config_unset(key: Annotated[str, typer.Argument(autocompletion=complete_config_keys)]):
    print(api.delete(f'config/{key}'))


# Git Keys
def complete_git_keys():
    keys = api.get('git-key')
    return [d['name'] for d in keys] if keys else []


git_key_app = typer.Typer(**typer_options)
app.add_typer(git_key_app, name="git-key", help="Manage Git-Keys")


@git_key_app.command(name='list', help='List all Git Keys')
def git_key_list():
    results = api.get('git-key')
    if not results:
        print("No Git Keys found")
        return

    table = Table(**table_options)

    for column in ['Name', 'Type', 'Updated']:
        table.add_column(column)

    for r in results:
        table.add_row(r['name'], r['auth_type'], time_since(r['updated_at']))
    console.print(table)


@git_key_app.command(name='view', help='View Git Key')
def git_key_view(name: Annotated[str, typer.Argument(autocompletion=complete_git_keys)]):
    result = api.get(f'git-key/{name}')
    print_kv(result)


@git_key_app.command(name='create', help='Create a new Git Key')
def git_key_create(name: Annotated[str | None, typer.Argument()] = None,
                   auth_type: Annotated[str | None, typer.Option('--type')] = None,
                   auth_key: Annotated[str | None, typer.Option('--key')] = None,
                   key_file: Annotated[
                       typer.FileText | None, typer.Option('--import', autocompletion=complete_files)] = None,
                   ):
    if key_file:
        auth_key = key_file.read()
        auth_type = 'ssh'
        if not name:
            name = key_file.name

    if not name:
        try:
            _default = '{}-key'.format(os.path.basename(os.getcwd()))
            name = questionary.text("Key Name", default=_default).unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)

    if not auth_type:
        try:
            auth_type = questionary.select("Authentication Method", choices=['ssh', 'pat']).unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)

    data = {
        'name': name,
        'auth_type': auth_type,
        'auth_key': auth_key,
    }

    if auth_type == 'pat' and not data['auth_key']:
        print("[red]authentication method [bold cyan]pat[/bold cyan] requires a value for --key[/red]")
        sys.exit(1)

    print(api.create('git-key', data=data))


@git_key_app.command(name='delete', help='Delete a Git Key')
def git_key_delete(name: Annotated[str | None, typer.Argument(autocompletion=complete_git_keys)] = None):
    if not name:
        name = questionary.select("Select Key", choices=complete_git_keys()).ask()
    if name:
        print(f"Deleting Git Key [bold cyan]{name}[/bold cyan]")
        console.print(api.delete(f'git-key/{name}'))


# Projects
project_app = typer.Typer(**typer_options)
app.add_typer(project_app, name="project", help="Manage Projects")


def complete_projects():
    _projects = api.get('project')
    return [p['name'] for p in _projects] if _projects else []


@project_app.command(name='list', help='List available Projects')
def project_list():
    projects = api.get('project')
    if not projects:
        print("No Projects found")
        return

    table = Table(**table_options)

    for column in ['Name', 'Remote', 'Key', 'Updated']:
        table.add_column(column)

    for p in projects:
        key = '-'
        if p['git_key']:
            key = '{auth_type}:{name}'.format(**p['git_key'])

        table.add_row(p['name'], p['remote'] or '-', key, time_since(p['updated_at']))
    console.print(table)


@project_app.command(name='view', help='get Projects details')
def project_view(name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
                 web: Annotated[bool | None, typer.Option('--web', help='Open Page in Browser')] = False):
    result = api.get(f'project/{name}')
    print_kv(result)

    if web:
        url = cliconfig['API_URL']
        console.print(f"Opening {url} ..")
        typer.launch(url)


def get_remote_from_git_config(path: str) -> str or None:
    git_config = Path(path, '.git', 'config')
    if os.path.isfile(git_config):
        with open(git_config, 'r', encoding='utf-8') as f:
            config = configparser.ConfigParser()
            config.read_file(f)
            if 'remote "origin"' in config:
                remote = config['remote "origin"']['url']
                print(f"[green]found remote origin:[/green] {remote}")
                return remote
    return


@project_app.command(name='create', help='Create a new Project')
def project_create(name: Annotated[str | None, typer.Argument()] = None,
                   remote: Annotated[str | None, typer.Option('--remote')] = None,
                   key: Annotated[str | None, typer.Option('--key', autocompletion=complete_git_keys)] = None):
    data = {}

    if not name:
        try:
            name = questionary.text("Enter a Project Name", default=os.path.basename(os.getcwd())).unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)

    if not name:
        print("Project Name cannot be empty")
        sys.exit(1)
    data['name'] = name

    if not remote:
        try:
            remote = questionary.text("Enter Git Remote", default='').unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)
    else:
        if os.path.isdir(remote):
            remote = get_remote_from_git_config(remote)

    if not remote:
        print(f"[red]no remote found[/red]")
        sys.exit(1)
    data['remote'] = remote

    if not key:
        if len(complete_config_keys()) > 0:
            print("[yellow]you have no git keys, skipping selection[/yellow]")
        else:
            try:
                key = questionary.select("Select a Git Key", choices=complete_git_keys()).unsafe_ask()
            except KeyboardInterrupt:
                sys.exit(1)

    if key:
        data['key'] = key

    if name:
        print(f"Creating project [bold cyan]{name}[/bold cyan]")
        result = api.create('project', data)
        print_kv(result)


@project_app.command(name='update', help='Update a Project')
def project_update(name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
                   remote: Annotated[str, typer.Option()] = None,
                   key: Annotated[str | None, typer.Option('--key', autocompletion=complete_git_keys)] = None):
    data = {}
    if not remote and not key:
        print("nothing to update, check --help for more info")
        sys.exit(1)

    if remote:
        if os.path.isdir(remote):
            remote = get_remote_from_git_config(remote)
        print(f"[green]found remote origin:[/green] {remote}")

    if remote:
        data['remote'] = remote

    if key:
        data['key'] = key

    print(f"Updating project [bold cyan]{name}[/bold cyan]")
    result = api.update(f'project/{name}', data)
    print_kv(result)


@project_app.command(name='delete', help='Delete a Project')
def project_delete(name: Annotated[str, typer.Argument(autocompletion=complete_projects)] = None):
    if not name:
        name = questionary.select("Select a Project for removal", choices=complete_projects()).ask()
    if name:
        print(f"Deleting project [bold cyan]{name}[/bold cyan]")
        console.print(api.delete(f'project/{name}'))


@project_app.command(name='deploy', help='Run deployment for Environment')
def project_deploy(
        name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
        environment: Annotated[str, typer.Argument()] = 'default',
):
    result = api.get(f'project/{name}/deploy/{environment}')
    print(result)


@project_app.command(name='status', help='Get deployment Status Environment')
def project_status(
        name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
        environment: Annotated[str, typer.Argument()] = 'default',
):
    result = api.get(f'project/{name}/status/{environment}')

    if 'ps' in result:
        table = Table(**table_options, title='Container')
        for col in ['Name', 'Image', 'State', 'Status']:
            table.add_column(col)
        for p in result['ps']:
            table.add_row(p['Name'], p['Image'], p['State'], p['Status'])
        console.print(table)

    if 'logs' in result:
        table = Table(**table_options, title='Logs', show_header=False)
        for line in result['logs'].split('\n'):
            table.add_row(line)
        console.print(table)


@project_app.command(name='refresh-token', help='Refresh Deployment Token')
def project_refresh_token(
        name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
):
    result = api.get(f'project/{name}/refresh-token')
    with console.status(f"Generating New Token for [bold cyan]{name}[/bold cyan]..."):
        print(f"Refreshing Project Deploy Token for [bold cyan]{name}[/bold cyan]")
        print(f"[yellow]{result['token']}[/yellow]")


# environments
env_app = typer.Typer(**typer_options)
app.add_typer(env_app, name="env", help="Manage Environments and Variables")


@env_app.callback()
def env_callback(
        ctx: typer.Context,
        project: Annotated[str, typer.Argument(autocompletion=complete_projects, show_default=False)],
):
    ctx.obj = SimpleNamespace(project=project)


@env_app.command('list', help='List Environments')
def env_list(
        ctx: typer.Context,
):
    table = Table(**table_options)
    print(f"environments for project [bold cyan]{ctx.obj.project}[/bold cyan]")
    envs = api.get(f'env/{ctx.obj.project}')

    if not envs:
        print("No Environments found")
        return
    for column in ['name', 'branch', 'Updated']:
        table.add_column(column)
    for p in envs:
        table.add_row(p['name'], p['branch'], time_since(p['updated_at']))
    console.print(table)


@env_app.command('view', help='Show Environment Variables')
def env_view(
        ctx: typer.Context,
        environment: Annotated[str | None, typer.Argument()] = None
):
    table = Table(**table_options)
    variables = api.get(f'env/{ctx.obj.project}/{environment}')
    print(f"Environment variables for [bold cyan]{environment}[/bold cyan]")  # for ")

    if not variables:
        print("No Variables found")
        return

    for column in ['KEY', 'VALUE', 'Updated']:
        table.add_column(column)
    for p in variables:
        table.add_row(p['key'], p['value'], time_since(p['updated_at']))

    console.print(table)


@env_app.command('create', help='Create an environment')  # , no_args_is_help=True)
def env_create(  # name: Annotated[str, typer.Argument()],
        ctx: typer.Context,
        environment: Annotated[str | None, typer.Argument()] = None,
        branch: Annotated[str | None, typer.Option('--branch')] = None,
):
    if not environment:
        environment = questionary.text("Enter Environment Name").ask()

    if not branch:
        branch = questionary.text("Enter corresponding Branch", default='main').ask()

    if environment and branch:
        print(
            f"Creating environment [cyan]{environment}[/cyan] ([green]{branch}[/green]) for [magenta]{ctx.obj.project}[/magenta]")
        result = api.create(f'env/{ctx.obj.project}', data={'name': environment, 'branch': branch})
        print_kv(result)


@env_app.command('update', help='Update an environment')
def env_update(
        ctx: typer.Context,
        environment: Annotated[str | None, typer.Argument()] = None,
        branch: Annotated[str | None, typer.Option('--branch')] = None,
):
    print(f"Updating Environment [bold cyan]{environment}[/bold cyan]")
    data = {}
    if not branch:
        print("nothing to update, check --help for more info")
        sys.exit(1)
    if branch:
        data['branch'] = branch
    console.print(api.update(f'env/{ctx.obj.project}/{environment}', data=data))


@env_app.command('delete', help='Delete an environment')
def env_delete(
        ctx: typer.Context,
        environment: Annotated[str | None, typer.Argument()] = None,
):
    if not environment:
        envs = api.get(f'env/{ctx.obj.project}')
        environment = questionary.rawselect("Select an Environment for removal", choices=envs).ask()

    if environment:
        print(f"Deleting {environment} for {ctx.obj.project}")
        print(api.delete(f'env/{ctx.obj.project}/{environment}'))


@env_app.command('set', help='Set an environment variable', no_args_is_help=True)
def env_set(
        ctx: typer.Context,
        environment: str = typer.Argument(default='default'),
        key: str = typer.Argument(),
        value: str = typer.Argument(),

):
    key = key.upper()
    print(ctx.obj.project, environment, key, value)
    print(f"{key}={value}")
    print(
        api.update(f'env/{ctx.obj.project}/{environment}', data={'key': key, 'value': value})
    )


@env_app.command('unset', help='Delete an environment or variable')
def env_unset(
        ctx: typer.Context,
        environment: str = typer.Argument(default='default'),
        key: str = typer.Argument(),
):
    print(f"{key} on {environment} for {ctx.obj.project}")
    print(
        api.delete(f'env/{ctx.obj.project}/{environment}/{key}')
    )


@env_app.command('import', help='Import environment variables from file')
def env_import(
        ctx: typer.Context,
        environment: Annotated[str, typer.Argument()],
        file: Annotated[typer.FileText, typer.Argument(autocompletion=complete_files)],
):
    print(
        f"importing [yellow]{file.name}[/yellow] to environment [red]{environment}[/red] for [bold cyan]{ctx.obj.project}[/bold cyan]")
    imported_env = dotenv_values(stream=file)
    for key, value in imported_env.items():
        print(f"set [bold cyan]{key}[/bold cyan]: {value} .. ", end='')
        api.update(f'env/{ctx.obj.project}/{environment}', data={'key': key, 'value': value})
        print("[bold][[green]OK[/green]][/bold]")


# Pages
page_app = typer.Typer(**typer_options)
app.add_typer(page_app, name="page", help="Manage Static Pages")


def complete_pages():
    _pages = api.get('page')
    if _pages:
        return [p['fqdn'] for p in _pages]
    return []


@page_app.command('list', help='List pages')
def page_list():
    pages = api.get('page')

    if not pages:
        print("No Pages found")
        return

    table = Table(**table_options)

    for column in ['FQDN', 'Updated']:
        table.add_column(column)

    for p in pages:
        table.add_row(p['fqdn'], time_since(p['updated_at']))

    console.print(table)


@page_app.command('create', help='Create new page')
def page_create(fqdn: Annotated[str, typer.Argument(help='FQDN')],
                redirects: Annotated[typing.List[str] | None, typer.Option(help="--redirects")] = None):
    print(f"Creating page [bold cyan]{fqdn}[/bold cyan]")
    print(api.create('page', data={'fqdn': fqdn}))

    if redirects:
        for redirect in redirects:
            print(f"Creating Redirect: {redirect}")
            result = api.create('redirect', data={'source': redirect, 'destination': fqdn})


@page_app.command('delete', help='Delete page')
def page_delete(fqdn: Annotated[str | None, typer.Argument(help='FQDN', autocompletion=complete_pages)] = None):
    if not fqdn:
        fqdn = questionary.select("Select a Page for removal", choices=complete_pages()).ask()
    if fqdn:
        print(f"Deleting Page [bold cyan]{fqdn}[/bold cyan]")
        console.print(api.delete(f'page/{fqdn}'))


@page_app.command('refresh-token', help='Refresh token')
def page_refresh_token(fqdn: Annotated[str, typer.Argument(help='FQDN', autocompletion=complete_pages)]):
    result = api.get(f'page/{fqdn}/refresh-token')
    with console.status(f"Generating New Token for [bold cyan]{fqdn}[/bold cyan]..."):
        print(f"Refreshing Page Deploy Token for [bold cyan]{fqdn}[/bold cyan]")
        print(f"[yellow]{result['token']}[/yellow]")


@page_app.command('deploy', help='Deploy page')
def page_deploy(fqdn: Annotated[str, typer.Argument(help='FQDN', autocompletion=complete_pages)],
                # file: Annotated[typer.FileBinaryRead, typer.Argument()],
                # file: Annotated[typer.FileBinaryRead, typer.Argument(autocompletion=complete_files)],
                path: Path = typer.Argument(None, file_okay=True, resolve_path=True, autocompletion=complete_files),
                view: Annotated[bool, typer.Option('--view', help='view URL')] = False):
    print(f"Deploying page [bold green]{fqdn}[/bold green]")

    if os.path.isdir(path):
        print("can't directory yet, please tar cvf payload.tar folder/")
        sys.exit(1)

    with console.status(f"Uploading [bold cyan]{"filename"}[/bold cyan]..."):
        with open(path, 'rb') as file:
            response = api.upload(f'page/{fqdn}/deploy', file=file)

        url = f'https://{fqdn}/'
        console.print("Successfully Uploaded")

    console.print(":heavy_check_mark-emoji: :rocket-emoji: Deployed ", url)
    if view:
        typer.launch(url)


# Redirects
redirect_app = typer.Typer(**typer_options)
app.add_typer(redirect_app, name="redirect", help="Manage Redirects")


@redirect_app.command('list', help='List Redirects')
def redirect_list():
    redirects = api.get('redirect')

    if not redirects:
        print("No Redirects found")
        return

    table = Table(**table_options)

    for column in ['Source', 'Destination', 'Updated']:
        table.add_column(column)

    for p in redirects:
        table.add_row(p['source'], p['destination'], time_since(p['updated_at']))

    console.print(table)


@redirect_app.command('create', help='Delete Redirects')
def redirect_create(
        source: Annotated[str, typer.Argument(help='FQDN')],
        destination: Annotated[str, typer.Argument(help='FQDN')]
):
    print(api.create(f'redirect', data={'source': source, 'destination': destination}))


@redirect_app.command('update', help='Update Redirect')
def redirect_update(
        source: Annotated[str, typer.Argument(help='FQDN')],
        destination: Annotated[str, typer.Argument(help='FQDN')]
):
    print(api.update(f'redirect/{source}', data={'destination': destination}))


@redirect_app.command('delete', help='Delete Redirects')
def redirect_delete(fqdn: Annotated[str, typer.Argument(help='FQDN')]):
    print(api.delete(f'redirect/{fqdn}'))


if __name__ == "__main__":
    app()
