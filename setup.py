from distutils.core import setup

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
  name = 'SCgraph',
  packages = ['SCgraph'],
  version = '0.1.0',
  license='MIT',
  description = 'Determine an approximate travel route between two points on earth',
  long_description=long_description,
  long_description_content_type='text/markdown',
  author = 'Connor Makowski',
  author_email = 'connor.m.makowski@gmail.com',
  url = 'https://github.com/connor-makowski/SCgraph',
  download_url = 'https://github.com/connor-makowski/pamda/dist/pamda-2.1.2.tar.gz',
  keywords = ['SCgraph'],
  install_requires=[
        "type_enforced>=0.0.15"
  ],
  classifiers=[
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Developers',
    'Topic :: Software Development :: Build Tools',
    'License :: OSI Approved :: MIT License',
    'Programming Language :: Python :: 3',
  ],
)
