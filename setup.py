from distutils.core import setup

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
  name = 'scgraph',
  packages = ['scgraph', 'scgraph.geographs'],
  version = '1.3.0',
  license='MIT',
  description = 'Determine an approximate route between two points on earth',
  long_description=long_description,
  long_description_content_type='text/markdown',
  author = 'Connor Makowski',
  author_email = 'connor.m.makowski@gmail.com',
  url = 'https://github.com/connor-makowski/scgraph',
  download_url = 'https://github.com/connor-makowski/scgraph/dist/scgraph-1.3.0.tar.gz',
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
