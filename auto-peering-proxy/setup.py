from setuptools import setup

setup(
    name='autoproxy',
    version='0.1',
    description='Automatic haproxy reconfigurator.',
    packages=['autoproxy'],
    install_requires=[
        'boto3',
        'jinja2',
    ],
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'autoproxy-generate=autoproxy.generate:main',
            'autoproxy-configure=autoproxy.conflagrate:main',
        ]
    }
)

