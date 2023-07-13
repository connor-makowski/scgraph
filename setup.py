from distutils.core import setup
from setuptools import find_packages

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
  name = 'scgraph',
  packages = find_packages(),
  version = '0.2.0',
  license='MIT',
  description = 'Determine an approximate route between two points on earth',
  long_description=long_description,
  long_description_content_type='text/markdown',
  author = 'Connor Makowski',
  author_email = 'connor.m.makowski@gmail.com',
  url = 'https://github.com/connor-makowski/scgraph',
  download_url = 'https://github.com/connor-makowski/scgraph/dist/scgraph-0.2.0.tar.gz',
  keywords = ['scgraph'],
  install_requires=[],
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
  ],
)
