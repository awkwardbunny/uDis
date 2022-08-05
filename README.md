# µDis
MicroPython Decompiler

Currently uses v1.18 release of [MicroPython](https://github.com/micropython/micropython), which uses bytecode version 5 ([doc](http://docs.micropython.org/en/latest/reference/mpyfiles.html#versioning-and-compatibility-of-mpy-files))

Disassembly works.  
Decompile not working yet.

## Running from source
Requires Python 3.10 or higher for 'match' ([PEP 636](https://peps.python.org/pep-0636/)).
Consider using the [docker method](#running-with-docker) below.

```bash
$ git clone https://github.com/awkwardbunny/uDis.git
$ cd uDis
$ pip3 install -r requirements.txt
$ cp <compiled mpy files> in/   # Place mpy files inside 'in/' directory
$ ls in/
hello_world.mpy test.mpy
$ ./main.py in out
$ ls out/
hello_world.py hello_world.s test.py test.s
```

## Running with Docker
Alternatively, if setting up Python 3.10+ is an issue, Docker can be used.

```bash
$ docker run -it -rm -v <path containing mpy files>:/code/in -v <output dir>:/code/out ghcr.io/awkwardbunny/udis:main
```
