from setuptools import setup, find_packages

setup(
    name='ai_ticket',
    version='0.1.0',
    packages=find_packages(where='src'),
    package_dir={'': 'src'},
    include_package_data=True,
    description='AI Ticket system to handle AI interactions with tickets.',
    author='jmikedupont2',
    author_email='jmikedupont2@example.com',
    url='https://github.com/jmikedupont2/ai-ticket',
    install_requires=[
        'anyio>=3.7',
        'httpx>=0.24',
        'fastapi>=0.110',
        'python-dotenv',
        'requests',
        'uvicorn[standard]>=0.22',
    ],
    entry_points={
        'console_scripts': ['ai-ticket=ai_ticket.cli:main'],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
    zip_safe=False,
)
