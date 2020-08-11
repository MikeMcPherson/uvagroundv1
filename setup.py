import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(name="uvagroundv1",
      version="1.6",
      author="Michael R. McPherson",
      author_email="mcpherson@acm.org",
      description="UVa Libertas Ground Station",
      long_description=long_description,
      long_description_content_type="text/markdown",
      url="https://github.com/MikeMcPherson/uvagroundv1",
      packages=setuptools.find_packages(),
      install_requires=[
            "requests",
            "pyserial",
            "hexdump",
            "simonspeckciphers",
            "construct",
            "nltk",
            "pycairo",
            "PyGObject"
      ],
      classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
            "Operating System :: OS Independent",
      ],
      python_requires='>=3.6',
)
