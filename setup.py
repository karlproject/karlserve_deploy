__version__ = '0.6dev'

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
      upgrade = karlserve_deploy.upgrade:config_upgrade
      migrate = karlserve_deploy.upgrade:config_migrate
      cleanup = karlserve_deploy.cleanup:config_parser
      """
      )

