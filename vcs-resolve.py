#!/usr/bin/env python3
import abc
import os
import re
from subprocess import check_call, check_output, CalledProcessError, STDOUT
import sys
import tempfile
from urllib.parse import quote, urlparse


class Repo(metaclass=abc.ABCMeta):

    COMMIT_RE = re.compile(r'[a-f0-9]{7,}')

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
        except (CalledProcessError, FileNotFoundError):
            return False

    @property
    def toplevel(self):
        return self._git('rev-parse --show-toplevel')

    @property
    def branch(self):
        try:
            # Try to get the remote branch first
            remote = self._git('rev-parse --abbrev-ref @{u}')
            if remote.startswith('remotes/'):
                remote = remote[len('remotes/'):]
            return remote.split('/', 1)[-1]
        except Exception:
            # Fall back to the local branch name, although this is
            # pretty useless
            return self._git('rev-parse --abbrev-ref @')

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
        except (CalledProcessError, FileNotFoundError):
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

    LINE_SEP = True

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
        for cls in [
                GitHub, BitBucket,
                Kiln, YGGitLab,
                RocheBitBucket,
                RocheGitLab,
                RocheTFS,
        ]:
            if cls.can_resolve(origin):
                return cls(repo)

        raise ValueError('Unknown resolver: {}'.format(origin))


class GitResolver(Resolver):

    HOSTNAME = None
    URL_FMT = 'https://{hostname}/{user}/{repo}'
    BLOB_FMT = '/blob/{branch}/{path}'
    COMMIT_FMT = '/commit/{commit}'

    LINE_SEP_FROM = '#L'
    LINE_SEP_TO = '-L'

    @classmethod
    def can_resolve(cls, origin):
        if cls.HOSTNAME in origin.scheme:
            return True

        if cls.HOSTNAME in origin.netloc:
            return True

        if cls.HOSTNAME in origin.path:
            return True

        return False

    def resolve(self, what):
        url = self.URL_FMT.format(
            hostname=self.HOSTNAME, user=self.user, repo=self.repo)
        p, is_commit = self.get_path(what)
        if is_commit:
            url += self.COMMIT_FMT.format(commit=p)
        elif p:
            url += self.BLOB_FMT.format(branch=self._repo.branch, path=quote(p))
        return url

    @property
    def repo_path(self):
        origin = self._repo.origin.path
        if origin.endswith('.git'):
            origin = origin[:-4]
        if self.HOSTNAME + ':' in origin:
            origin = origin.split(':', 1)[-1]
        return origin

    @property
    def user(self):
        return self.repo_path.strip('/').split('/')[0]

    @property
    def repo(self):
        return self.repo_path.strip('/').split('/', 1)[1]

    def _adjust_lines(self, p):
        if ':' in p:
            idx = p.index(':')
            if self.LINE_SEP:
                p = ''.join([
                    p[:idx],
                    p[idx:].replace(
                        ':', self.LINE_SEP_FROM
                    ).replace(
                        ',', self.LINE_SEP_TO
                    )
                ])
            else:
                p = p[:idx]
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


class GitHub(GitResolver):

    HOSTNAME = 'github.com'


class YGGitLab(GitResolver):

    HOSTNAME = 'gitlab.yougov.net'
    LINE_SEP_TO = '-'


class BitResolver(Resolver):

    HOSTNAME = None
    URL_FMT = None
    BLOB_FMT = None
    COMMIT_FMT = None

    @classmethod
    def can_resolve(cls, origin):
        if origin.scheme in ['bitbucket', 'bb']:
            return True

        if cls.HOSTNAME in origin.scheme:
            return True

        if cls.HOSTNAME in origin.netloc:
            return True

        if cls.HOSTNAME in origin.path:
            return True

        return False

    @property
    def repo_path(self):
        return self._repo.origin.path

    @property
    def user(self):
        return self.repo_path.strip('/').split('/')[0]

    @property
    def repo(self):
        git_repo = self.repo_path.strip('/').split('/')[1]
        if git_repo.endswith('.git'):
            git_repo = git_repo[:-4]
        return git_repo

    def get_path(self, what):
        if self._repo.is_commit(what):
            p = what
            is_commit = True
        else:
            p = self._repo.relpath(what)
            is_commit = False
        p = self._split_lines(p)
        return p, is_commit


class BitBucket(BitResolver):
    HOSTNAME = 'bitbucket.org'
    URL_FMT = 'https://{hostname}/{user}/{repo}'
    BLOB_FMT = '/src/{changeset}/{path}?at={branch}'
    COMMIT_FMT = '/commits/{commit}'

    def resolve(self, what):
        url = self.URL_FMT.format(
            hostname=self.HOSTNAME, user=self.user, repo=self.repo)
        (p, lines), is_commit = self.get_path(what)
        if is_commit:
            url += self.COMMIT_FMT.format(commit=p)
        else:
            url += self.BLOB_FMT.format(
                changeset=self._repo.changeset,
                branch=self._repo.branch, path=p)
        return url + lines

    @staticmethod
    def _split_lines(p):
        if ':' in p:
            idx = p.index(':')
            fname = os.path.basename(p[:idx])
            return p[:idx], p[idx:].replace(
                ':', '#' + fname + '-').replace(',', ':')
        return p, ''


class RocheBitBucket(BitResolver):
    HOSTNAME = 'bitbucket.roche.com'
    URL_FMT = 'https://{hostname}/stash/{repo_type}/{user}/repos/{repo}'
    BLOB_FMT = '/browse/{path}?at={branch}'
    COMMIT_FMT = '/commits/{commit}'

    def resolve(self, what):
        url = self.URL_FMT.format(
            hostname=self.HOSTNAME, user=self.user, repo=self.repo,
            repo_type=self.repo_type)
        (p, lines), is_commit = self.get_path(what)
        if is_commit:
            url += self.COMMIT_FMT.format(commit=p)
        else:
            url += self.BLOB_FMT.format(
                branch=self._repo.branch, path=quote(p))
        return url + lines

    @property
    def user(self):
        return self.repo_path.strip('/').strip('~').split('/')[0]

    @property
    def repo_type(self):
        path = self.repo_path.strip('/')
        if path.startswith('~'):
            return 'users'
        return 'projects'

    @staticmethod
    def _split_lines(p):
        if ':' in p:
            idx = p.index(':')
            fname = os.path.basename(p[:idx])
            return p[:idx], p[idx:].replace(':', '#').replace(',', '-')
        return p, ''


class RocheGitLab(GitResolver):

    HOSTNAME = 'code.roche.com'
    LINE_SEP_TO = '-'

    @property
    def repo_path(self):
        origin = self._repo.origin.path
        if origin.endswith('.git'):
            origin = origin[:-4]
        if self.HOSTNAME + ':' in origin:
            origin = origin.split(':', 1)[-1]
        return origin


class RocheTFS(GitResolver):

    HOSTNAME = 'tfsprod.emea.roche.com'
    LINE_SEP = False
    BLOB_FMT = '?path={path}&version=GB{branch}'

    @property
    def repo_path(self):
        origin = self._repo.origin.path
        if origin.endswith('.git'):
            origin = origin[:-4]
        if self.HOSTNAME + ':' in origin:
            origin = origin.split(':', 1)[-1]
        return origin


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
            path=quote(p)) + lines


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
