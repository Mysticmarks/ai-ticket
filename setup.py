from setuptools import setup, find_packages

setup(
    name='ai_ticket',
    version='0.1.0',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    description='AI Ticket system to handle AI interactions with tickets.',
    author='jmikedupont2',
    author_email='jmikedupont2@example.com',
    url='https://github.com/jmikedupont2/ai-ticket',
    install_requires=[
        'python-dotenv',
        'requests',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
)
