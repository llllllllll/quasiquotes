#!/usr/bin/env python
import os
from setuptools import setup, find_packages, Extension
from setuptools.command.install import install
from setuptools.command.develop import develop
from shutil import copy
import sys

long_description = ''

if 'upload' in sys.argv:
    with open('README.rst') as f:
        long_description = f.read()


def subcmd(cmd):
    class sub(cmd):

        @property
        def __path(self):
            try:
                return self.shadow_path[1]
            except AttributeError:
                return self.install_lib

        __file = 'quasiquotes.pth'

        def run(self):
            self.path_file = 'quasiquotes'
            super().run()
            self.execute(copy, (self.__file, self.__path))

        def uninstall_link(self):
            self.execute(
                os.remove,
                (os.path.join(self.__path, self.__file),),
            )
            super().uninstall_link()

    return sub


setup(
    cmdclass={'install': subcmd(install), 'develop': subcmd(develop)},
    name='quasiquotes',
    version='0.2.1',
    description='Quasiquotation in python',
    author='Joe Jevnik',
    author_email='joejev@gmail.com',
    packages=find_packages(),
    long_description=long_description,
    license='GPL-2',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Software Development :: Pre-processors',
    ],
    ext_modules=[
        Extension('quasiquotes.c._loader', ['quasiquotes/c/_loader.c']),
    ],
    url='https://github.com/llllllllll/quasiquotes',
    extras_require={
        'r': ['rpy2'],
    },
)
