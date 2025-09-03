#!/usr/bin/env python3
import configparser
import os
import re
import sys
import typing
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

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
from typing_extensions import Annotated, Literal

CONFIG_DIR = Path.home() / '.config/ccd/'

DEFAULT_CONFIG = {
    'API_URL': 'http://localhost:8001',
    'API_KEY': 'root',
}

GITHUB_REPO_PATTERN = r'^(?P<user>[\w\d-]+)/(?P<repo>[\w\d-]+)(?:@(?P<branch>[\w.\-/]+))?$'

SUCCESS = "[bold bright_green]:heavy_check_mark:[/bold bright_green]"
FAIL = "[bold bright_red]:cross_mark:[/bold bright_red]"


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

    def request(self,
                method: Literal['GET', 'POST', 'PUT', 'DELETE'],
                path: str,
                raw_data: dict | None = None,
                data: dict | None = None,
                files=None):
        url = '/'.join([self.api_url, path])
        try:
            r = requests.request(method, url, headers=self.headers, json=data,
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


def print_result_details(result):
    if 'detail' in result:
        console.print(f"{FAIL} {result['detail']}")
    else:
        console.print(f"{SUCCESS}")


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
HELP_CONFIG = """
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


def print_table(result: dict, columns: list, fields):
    if not result:
        print("No Results")
        return

    table = Table(**table_options)  # box=None) # , show_header=False)

    for column in columns:
        table.add_column(column.upper())

    for r in result:
        row = []
        for field in fields:
            if not r.get(field):
                row.append('-')
            elif field.endswith('_at'):
                row.append(time_since(r[field]))
            elif r[field].startswith('git@github.com:'):
                row.append(r[field].strip('git@github.com:'))
            else:
                row.append(r[field])
        table.add_row(*row)
    console.print(table)


@config_app.command('list', help='list config')
def config_list():
    result = api.get('config')
    print_table(result, ['Key', 'Value'], ['key', 'value'])


@config_app.command('set', help='set config')
def config_set(key: Annotated[str, typer.Argument(autocompletion=complete_config_keys)], value: str):
    print(api.update('config', {'key': key, 'value': value}))


@config_app.command('unset', help='unset config')
def config_unset(key: Annotated[str, typer.Argument(autocompletion=complete_config_keys)]):
    print(api.delete(f'config/{key}'))


# Git Keys
def complete_auth():
    keys = api.get('auth')
    return [d['name'] for d in keys] if keys else []


auth_app = typer.Typer(**typer_options)
app.add_typer(auth_app, name="auth", help="Manage Authentication Keys")


@auth_app.command(name='list', help='show all Keys')
def auth_list(filter: Annotated[str, typer.Argument()] = ''):
    result = api.get(f'auth?filter_by={filter}')
    if not result:
        print("No Authentication Keys found")
        return
    print_table(result, ['Name', 'Type', 'Updated'], ['name', 'auth_type', 'updated_at'])


@auth_app.command(name='view', help='show Key details')
def auth_view(name: Annotated[str, typer.Argument(autocompletion=complete_auth)]):
    result = api.get(f'auth/{name}')
    print_kv(result)


@auth_app.command(name='create', help='create Key')
def auth_create(name: Annotated[str | None, typer.Argument()] = None,
                ssh: Annotated[bool | None, typer.Option('--ssh')] = None,
                pat: Annotated[str | None, typer.Option('--pat')] = None,
                import_file: Annotated[
                    typer.FileText | None, typer.Option('--import', autocompletion=complete_files)] = None,
                ):
    auth_type = None
    auth_key = None

    if import_file:
        auth_type = 'ssh'
        auth_key = import_file.read()
        if not name:
            name = import_file.name
    elif ssh:
        auth_type = 'ssh'
    elif pat:
        auth_type = 'pat'
        auth_key = pat
    else:
        try:
            auth_type = questionary.select("Authentication Method", choices=['ssh', 'pat']).unsafe_ask()
            if auth_type == 'pat':
                auth_key = questionary.text("PAT").unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)

    data = {
        'name': name.replace(' ', '_') if name else None,
        'auth_type': auth_type,
        'auth_key': auth_key,
    }

    result = api.create('auth', data=data)
    if auth_type == 'ssh' and result.get('public_key'):
        print(result['public_key'])
    else:
        print_kv(result)


@auth_app.command(name='delete', help='delete Key')
def auth_delete(name: Annotated[str | None, typer.Argument(autocompletion=complete_auth)] = None):
    if not name:
        name = questionary.select("Select Key", choices=complete_auth()).ask()
    if name:
        print(f"Deleting Git Key [bold cyan]{name}[/bold cyan]")
        console.print(api.delete(f'auth/{name}'))


# Projects
project_app = typer.Typer(**typer_options)
app.add_typer(project_app, name="project", help="Manage Projects")


def get_remote_from_git_config(path: str) -> str:
    git_config = Path(path, '.git', 'config')
    if os.path.isfile(git_config):
        with open(git_config, 'r', encoding='utf-8') as f:
            config = configparser.ConfigParser()
            config.read_file(f)
            if 'remote "origin"' in config:
                remote = config['remote "origin"']['url']
                print(f"[green]found remote origin:[/green] {remote}")
                return remote
    return ''


def parse_remote(remote, branch):
    match = re.match(GITHUB_REPO_PATTERN, remote)
    if match:
        remote = f"git@github.com:{match.group('user')}/{match.group('repo')}.git"
        if not branch:
            if match.group('branch'):
                branch = match.group('branch')
    return remote, branch


def complete_projects():
    _projects = api.get('project')
    return [p['name'] for p in _projects] if _projects else []


@project_app.command(name='list', help='List available Projects')
def project_list(filter: Annotated[str, typer.Argument()] = ''):
    result = api.get(f'project?filter_by={filter}')
    if not result:
        print("No Projects found")
        return

    print_table(result, ['Name', 'Remote', 'Branch', 'Key', 'Updated'],
                ['name', 'remote', 'branch', 'key', 'updated_at'])


@project_app.command(name='view', help='show Projects details')
def project_view(project: Annotated[str, typer.Argument(autocompletion=complete_projects)],
                 secrets: Annotated[bool | None, typer.Option('--secrets', help='Show Project Secrets')] = False,
                 web: Annotated[bool | None, typer.Option('--web', help='Open Page in Browser')] = False):
    if secrets:
        result = api.get(f'secret/{project}')
        print(f"Secrets for [bold bright_cyan]{project}[/bold bright_cyan]")  # for ")
        print_table(result, ['KEY', 'VALUE', 'Updated'], ['key', 'value', 'updated_at'])

    else:
        result = api.get(f'project/{project}')
        print_kv(result)

    if web:
        url = cliconfig['API_URL']
        console.print(f"Opening {url} ..")
        typer.launch(url)


@project_app.command(name='create', help='create a new Project')
def project_create(name: Annotated[str | None, typer.Argument()] = None,
                   remote: Annotated[str | None, typer.Option('--remote')] = None,
                   branch: Annotated[str | None, typer.Option('--branch')] = None,
                   key: Annotated[str | None, typer.Option('--key', autocompletion=complete_auth)] = None):
    # remote and branch
    if not remote:
        try:
            remote = questionary.text("Enter Git Remote", default='').unsafe_ask()
        except KeyboardInterrupt:
            sys.exit(1)

    if remote:
        if os.path.isdir(remote):
            remote = get_remote_from_git_config(remote)
        else:
            remote, branch = parse_remote(remote, branch)
            print(remote, branch)
    else:
        print("[red]no remote found[/red]")
        sys.exit(1)

    if name == '.':
        name = Path('.').resolve().name

    data = {
        'name': name.replace('/', '-') if name else None,
        'remote': remote,
        'branch': branch,
    }

    # authentication key
    if not key:
        if len(complete_config_keys()) > 0:
            print("[yellow]you have no git keys, skipping selection[/yellow]")
        else:
            try:
                key = questionary.select("Select a Git Key", choices=complete_auth()).unsafe_ask()
            except KeyboardInterrupt:
                sys.exit(1)
    if key:
        data['key'] = key

    with console.status("Creating Project.. ", refresh_per_second=20):
        result = api.create('project', data)
        print(f"[bold bright_cyan]{result['name']}[/bold bright_cyan]")
    print_kv(result)


@project_app.command(name='update', help='Update a Project')
def project_update(project: Annotated[str, typer.Argument(autocompletion=complete_projects)],
                   remote: Annotated[str | None, typer.Option()] = None,
                   key: Annotated[str | None, typer.Option(autocompletion=complete_auth)] = None,
                   branch: Annotated[str | None, typer.Option()] = None,
                   set: Annotated[Optional[List[str]], typer.Option()] = None,
                   unset: Annotated[Optional[List[str]], typer.Option()] = None,
                   file: Annotated[
                       typer.FileText | None, typer.Option('--import-env', autocompletion=complete_files)] = None,
                   ):
    if not any([remote, key, branch, set, unset, file]):
        print("option required: --help")
        exit(1)

    data = {}

    # remote and branch
    if remote:
        if os.path.isdir(remote):
            remote = get_remote_from_git_config(remote)
        else:
            remote, branch = parse_remote(remote, branch)

        data['remote'] = remote

    if key:
        data['key'] = key

    if branch:
        data['branch'] = branch

    if remote or branch or key:
        print(f"Updating project [bold cyan]{project}[/bold cyan]")
        result = api.update(f'project/{project}', data)
        print_kv(result)

    # secrets
    if set:
        for s in set:
            try:
                key, value = s.split("=", 1)
            except ValueError:
                print(f"skipping {s}")
                continue

            with console.status("Pushing Secret.. ", refresh_per_second=20):
                result = api.update(f'secret/{project}', data={'key': key.upper(), 'value': value})
                print(f"[bold bright_cyan]{result['key']}[/bold bright_cyan] :heavy_check_mark:")

    if unset:
        for key in unset:
            with console.status("Deleting Secret.. ", refresh_per_second=20):
                result = api.delete(f'secret/{project}/{key}')
                print(f"[bold bright_cyan]{key}[/bold bright_cyan] :heavy_check_mark:")

    # import secrets from file
    if file:
        print(f"importing [yellow]{file.name}[/yellow]")
        imported_env = dotenv_values(stream=file)
        for key, value in imported_env.items():
            print(f"- [bold cyan]{key}[/bold cyan]: {value} .. ", end='')
            api.update(f'secret/{project}', data={'key': key, 'value': value})
            print("[bold green]:heavy_check_mark:[/bold green]")


@project_app.command(name='delete', help='Delete a Project')
def project_delete(name: Annotated[str | None, typer.Argument(autocompletion=complete_projects)] = None):
    if not name:
        name = questionary.select("Select a Project for removal", choices=complete_projects()).ask()
    if name:
        print(f"Deleting project [bold cyan]{name}[/bold cyan]")
        console.print(api.delete(f'project/{name}'))


@project_app.command(name='deploy', help='Run deployment for Environment')
def project_deploy(
        name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
        start: Annotated[bool, typer.Option('--start', help='start deployment')] = False,
        stop: Annotated[bool, typer.Option('--stop', help='stop deployment')] = False,
        status: Annotated[bool, typer.Option('--status', help='get status')] = False,
        logs: Annotated[bool, typer.Option('--logs', help='get logs')] = False,
):
    if status or logs:
        result = api.get(f'deploy/{name}/status')

        if status and 'ps' in result:
            print_table(
                result['ps'],
                ['Name', 'Image', 'State', 'Status'],
                ['Name', 'Image', 'State', 'Status'])

        if logs and 'logs' in result:
            table = Table(**table_options, show_header=False)
            for line in result['logs'].split('\n'):
                table.add_row(line)
            console.print(table)

    elif stop:
        result = api.get(f'deploy/{name}/stop')
    else:
        result = api.get(f'deploy/{name}/start')

    if 'detail' in result:
        print(result['detail'])


@project_app.command(name='status', help='Get deployment Status Environment')
def project_status(
        name: Annotated[str, typer.Argument(autocompletion=complete_projects)],
):
    result = api.get(f'project/{name}/status')

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
        print(f"New Deploy Token for [bold bright_cyan]{name}[/bold bright_cyan]")
        print(f"[bright_red]{result['token']}[/bright_red]")
    print('curl -X POST ' + os.path.join(cliconfig['API_URL'], 'webhook/project', result['token']))


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
    result = api.get('page')
    print_table(result, ['FQDN', 'Updated'], ['fqdn', 'updated_at'])


@page_app.command('create', help='Create new page')
def page_create(fqdn: Annotated[str, typer.Argument(help='FQDN')],
                cors_hosts: Annotated[typing.List[str] | None, typer.Option('--cors')] = None,
                redirect: Annotated[typing.List[str] | None, typer.Option('--redirect')] = None):
    console.print(f"Creating Page [bold bright_cyan]{fqdn}[/bold bright_cyan].. ", end='')
    hosts = None
    if cors_hosts:
        hosts = ','.join(cors_hosts)
    result = api.create('page', data={'fqdn': fqdn, 'cors_hosts': hosts})
    print_result_details(result)

    if redirect:
        for source in redirect:
            with console.status("Creating Redirect.. "):
                print(f"Redirect: {source}", end='')
                result = api.create('redirect', data={'source': source, 'destination': fqdn})
                print_result_details(result)


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
            api.upload(f'upload/{fqdn}', file=file)

        url = f'https://{fqdn}/'
        console.print("Successfully Uploaded")

    console.print(":heavy_check_mark: Deployed ", url)
    if view:
        typer.launch(url)


# Redirects
redirect_app = typer.Typer(**typer_options)
app.add_typer(redirect_app, name="redirect", help="Manage Redirects")


@redirect_app.command('list', help='List Redirects')
def redirect_list():
    result = api.get('redirect')
    print_table(result,
                ['Source', 'Destination', 'Updated'],
                ['source', 'destination', 'updated_at']
                )


@redirect_app.command('create', help='Delete Redirects')
def redirect_create(
        source: Annotated[str, typer.Argument(help='FQDN')],
        destination: Annotated[str, typer.Argument(help='FQDN')]
):
    print(api.create('redirect', data={'source': source, 'destination': destination}))


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
