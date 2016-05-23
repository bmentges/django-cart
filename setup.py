#!/usr/bin/env python

import os
from setuptools import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
        name='django-cart',
        version='1.0.4',
        description='Django simple shopping cart, tests and south migrations included',
        maintainer='Bruno Carvalho',
        maintainer_email='bmentges@gmail.com',
        license="GNU v3",
        url='https://github.com/bmentges/django-cart',
        packages=['cart', 'cart.migrations'],
        classifiers=[
            "Development Status :: 5 - Production/Stable", 
            "Environment :: Web Environment",
            "Framework :: Django",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: BSD License",
            "Operating System :: OS Independent",
            "Programming Language :: Python",
            "Topic :: Software Development :: Libraries :: Python Modules",
        ],
     )
