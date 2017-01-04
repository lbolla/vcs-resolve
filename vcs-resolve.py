#!/usr/bin/env python3
import abc
import os
import re
from subprocess import check_call, check_output, CalledProcessError, STDOUT
import sys
import tempfile
from urllib.parse import urlparse


class Repo(metaclass=abc.ABCMeta):

    COMMIT_RE = re.compile(r'[a-z0-9]{16}')

    def __init__(self, what):
        self.what = what
        self.resolver = Resolver.get(self)

    @staticmethod
    def get(what):
        if os.path.isdir(what):
            what_dir = what
        else:
            what_dir = os.path.dirname(what) or '.'

        os.chdir(what_dir)

        if Git.is_repo():
            return Git(what)

        if Hg.is_repo():
            return Hg(what)

        raise ValueError('Unknown repo: {}'.format(what))

    @property
    @abc.abstractmethod
    def origin(self):
        return None

    @staticmethod
    @abc.abstractmethod
    def is_repo():
        return False

    @property
    @abc.abstractmethod
    def toplevel(self):
        return None

    @property
    @abc.abstractmethod
    def branch(self):
        return None

    def is_commit(self, what):
        return self.COMMIT_RE.match(what) is not None

    def relpath(self, what):
        if what.startswith(self.toplevel):
            what = what[len(self.toplevel):]
        what = what.lstrip('/')
        if what == '.':
            what = ''
        return what

    def resolve(self):
        return self.resolver.resolve(self.what)


class Git(Repo):

    ORIGIN_RE = re.compile(r'^origin(.*)\(fetch\)$')

    @staticmethod
    def _git(cmd):
        output = check_output(['git'] + cmd.split(), stderr=STDOUT)
        return output.decode('utf-8').strip()

    @staticmethod
    def is_repo():
        try:
            Git._git('status')
            return True
        except CalledProcessError:
            return False

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


class Hg(Repo):

    ORIGIN_RE = re.compile(r'^default = (.*)$')

    @staticmethod
    def _hg(cmd):
        output = check_output(['hg'] + cmd.split(), stderr=STDOUT)
        return output.decode('utf-8').strip()

    @staticmethod
    def is_repo():
        try:
            Hg._hg('status')
            return True
        except CalledProcessError:
            return False

    @property
    def origin(self):
        output = self._hg('paths')
        for line in output.splitlines():
            m = self.ORIGIN_RE.match(line)
            if m is not None:
                path = m.groups()[0].strip()
                return urlparse(path)
        raise ValueError('Origin not found')

    @property
    def toplevel(self):
        return self._hg('root')

    @property
    def branch(self):
        return self._hg('branch')

    @property
    def changeset(self):
        return self._hg('id')


class Resolver(metaclass=abc.ABCMeta):

    def __init__(self, repo):
        self._repo = repo

    @staticmethod
    @abc.abstractmethod
    def can_resolve(origin):
        return False

    @abc.abstractmethod
    def resolve(self, what):
        pass

    @staticmethod
    def get(repo):
        origin = repo.origin
        for cls in [GitHub, BitBucket, Kiln]:
            if cls.can_resolve(origin):
                return cls(repo)

        raise ValueError('Unknown resolver: {}'.format(origin))


class GitHub(Resolver):

    URL_FMT = 'https://github.com/{user}/{repo}'
    BLOB_FMT = '/blob/{branch}/{path}'
    COMMIT_FMT = '/commit/{commit}'

    @staticmethod
    def can_resolve(origin):
        if origin.scheme in ['github', 'gh']:
            return True

        if 'github.com' in origin.netloc:
            return True

        if 'github.com' in origin.path:
            return True

        return False

    def resolve(self, what):
        url = self.URL_FMT.format(user=self.user, repo=self.repo)
        p, is_commit = self.get_path(what)
        if is_commit:
            url += self.COMMIT_FMT.format(commit=p)
        elif p:
            url += self.BLOB_FMT.format(branch=self._repo.branch, path=p)
        return url

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
        return self.repo_path.strip('/').split('/')[0]

    @property
    def repo(self):
        return self.repo_path.strip('/').split('/')[1]

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
        if self._repo.is_commit(what):
            p = what
            is_commit = True
        else:
            p = self._repo.relpath(what)
            is_commit = False
        p = self._adjust_lines(p)
        return p, is_commit


class BitBucket(Resolver):

    URL_FMT = 'https://bitbucket.org/{user}/{repo}'
    BLOB_FMT = '/src/{changeset}/{path}?at={branch}'
    COMMIT_FMT = '/commits/{commit}'

    @staticmethod
    def can_resolve(origin):
        if origin.scheme in ['bitbucket', 'bb']:
            return True

        if 'bitbucket.org' in origin.netloc:
            return True

        if 'bitbucket.org' in origin.path:
            return True

        return False

    def resolve(self, what):
        url = self.URL_FMT.format(user=self.user, repo=self.repo)
        (p, lines), is_commit = self.get_path(what)
        if is_commit:
            url += self.COMMIT_FMT.format(commit=p)
        else:
            url += self.BLOB_FMT.format(
                changeset=self._repo.changeset,
                branch=self._repo.branch, path=p)
        return url + lines

    @property
    def repo_path(self):
        return self._repo.origin.path

    @property
    def user(self):
        return self.repo_path.strip('/').split('/')[0]

    @property
    def repo(self):
        return self.repo_path.strip('/').split('/')[1]

    @staticmethod
    def _split_lines(p):
        if ':' in p:
            idx = p.index(':')
            fname = os.path.basename(p[:idx])
            return p[:idx], p[idx:].replace(
                ':', '#' + fname + '-').replace(',', ':')
        return p, ''

    def get_path(self, what):
        if self._repo.is_commit(what):
            p = what
            is_commit = True
        else:
            p = self._repo.relpath(what)
            is_commit = False
        p = self._split_lines(p)
        return p, is_commit


class Kiln(Resolver):

    URL_FMT = (
        'https://{user}.kilnhg.com/Code/{repo}/{path}'
        '?rev={branch}'
    )

    @staticmethod
    def can_resolve(origin):
        if origin.scheme in ['kiln']:
            return True

        if 'kilnhg.com' in origin.netloc:
            return True

        return False

    @property
    def user(self):
        return self._repo.origin.netloc.split('@', 1)[0]

    @property
    def repo(self):
        return self._repo.origin.path.lstrip('/')

    @staticmethod
    def _split_lines(p):
        if ':' in p:
            idx = p.index(':')
            return p[:idx], p[idx:].replace(':', '#').replace(',', '-')
        return p, ''

    @staticmethod
    def _rewrite_hidden_segments(p):
        '''Kiln uses IIS that does not allow "hidden segments".'''
        hidden_segments = {'bin'}
        tokens = []
        for t in p.split('/'):
            if t.strip() in hidden_segments:
                t = '%24{}%24'.format(t)
            tokens.append(t)
        return '/'.join(tokens)

    def get_path(self, what):
        if self._repo.is_commit(what):
            p = 'History/{}'.format(what)
        else:
            p = 'Files/{}'.format(self._repo.relpath(what))
            p = self._rewrite_hidden_segments(p)
        return self._split_lines(p)

    def resolve(self, what):
        p, lines = self.get_path(what)
        return self.URL_FMT.format(
            user=self.user, repo=self.repo, branch=self._repo.branch,
            path=p) + lines


def xdg_open(url):
    # Discard output
    _output = check_output(['xdg-open', url], stderr=STDOUT)


def save_x_clipboard(stuff):
    with tempfile.NamedTemporaryFile() as f:
        f.write(stuff.encode())
        f.flush()
        check_call('xclip -selection clipboard -i {}'.format(f.name).split())


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else '.'
    repo = Repo.get(what)
    url = repo.resolve()
    xdg_open(url)
    # TODO command arg to save to clipboard
    # save_x_clipboard(url)
    print(url)


if __name__ == '__main__':
    main()
