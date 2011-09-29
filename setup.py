__version__ = '0.3'

from setuptools import setup, find_packages

requires = [
    'karlserve'
]

setup(name='karlserve_deploy',
      version=__version__,
      description='Tools for Karl Production Install',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires = requires,
      entry_points = """\
      [karlserve.scripts]
      upgrade = karlserve_gocept.upgrade:config_upgrade
      migrate = karlserve_gocept.upgrade:config_migrate
      cleanup = karlserve_gocept.cleanup:config_parser
      """
      )

