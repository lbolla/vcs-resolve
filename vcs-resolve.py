#!/usr/bin/env python
import os
import re
from subprocess import check_call, check_output, CalledProcessError
import sys
import tempfile
from urllib.parse import urlparse


class Repo:
    pass


class Git(Repo):

    ORIGIN_RE = re.compile(r'^origin(.*)\(fetch\)$')

    def __init__(self, what):
        self.what = what
        self.resolver = get_resolver_cls(self.origin)(self)

    @staticmethod
    def is_git():
        try:
            Git._git('status')
            return True
        except CalledProcessError:
            pass

    @staticmethod
    def _git(cmd):
        output = check_output(['git'] + cmd.split())
        return output.decode('utf-8').strip()

    @property
    def toplevel(self):
        return self._git('rev-parse --show-toplevel')

    @property
    def branch(self):
        output = self._git('branch')
        for line in output.splitlines():
            if line.startswith('*'):
                return line[2:].strip()
        raise ValueError('Branch not found: {}'.format(output))

    @property
    def origin(self):
        output = self._git('remote -v')
        for line in output.splitlines():
            m = self.ORIGIN_RE.match(line)
            if m is not None:
                path = m.groups()[0].strip()
                return urlparse(path)
        raise ValueError('Origin not found')

    def resolve(self):
        return self.resolver.resolve(self.what)


class Resolver:

    def __init__(self, repo):
        self._repo = repo


class GitHub(Resolver):

    URL_FMT = 'https://github.com/{user}/{repo}/blob/{branch}/{path}'

    @property
    def repo_path(self):
        origin = self._repo.origin.path
        if origin.endswith('.git'):
            origin = origin[:-4]
        if 'github.com:' in origin:
            origin = origin.split(':', 1)[-1]
        return origin

    @property
    def user(self):
        return self.repo_path.split('/')[0]

    @property
    def repo(self):
        return self.repo_path.split('/')[1]

    @staticmethod
    def _adjust_lines(p):
        if ':' in p:
            idx = p.index(':')
            p = ''.join([
                p[:idx],
                p[idx:].replace(':', '#L').replace(',', '-L')
            ])
        return p

    def get_path(self, what):
        p = what[len(self._repo.toplevel):].lstrip('/')
        p = self._adjust_lines(p)
        return p

    def resolve(self, what):
        return self.URL_FMT.format(
            user=self.user, repo=self.repo, branch=self._repo.branch,
            path=self.get_path(what))


def get_repo(what):
    os.chdir(os.path.dirname(what))
    if Git.is_git():
        return Git(what)
    raise ValueError('Unknown repo: {}'.format(what))


def get_resolver_cls(origin):
    if origin.scheme in ['github', 'gh']:
        return GitHub

    if 'github.com' in origin.path:
        return GitHub

    raise ValueError('Unknown resolver: {}'.format(origin))


def xdg_open(url):
    check_call(['xdg-open', url])


def save_x_clipboard(stuff):
    with tempfile.NamedTemporaryFile() as f:
        f.write(stuff.encode())
        f.flush()
        check_call('xclip -selection clipboard -i {}'.format(f.name).split())


def main():
    what = sys.argv[1]
    repo = get_repo(what)
    url = repo.resolve()
    # xdg_open(url)
    # save_x_clipboard(url)
    print(url)


if __name__ == '__main__':
    main()
