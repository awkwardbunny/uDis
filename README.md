# µDis
MicroPython Decompiler

Currently uses v1.18 release of [MicroPython](https://github.com/micropython/micropython), which uses bytecode version 5 ([doc](http://docs.micropython.org/en/latest/reference/mpyfiles.html#versioning-and-compatibility-of-mpy-files))

The bytecode is generated from MicroPython itself. The `micropython/micropython` binary is the built Unix port of the MicroPython interpreter. Docs on building it can be found [here](https://docs.micropython.org/en/latest/develop/gettingstarted.html#building-the-unix-port-of-micropython)

Bytecode version 6 for MicroPython v1.19+ should be fairly easy to support by replacing `micropython/micropython` binary (and maybe minor modifications to `main.py`).

Disassembly works.
Decompile not working yet.

## Understanding the Python Bytecode
The program will output the disassembled bytecode and decompiled source.
As decompilation isn't working, all we have is the disassembly.

The reference for all the bytecode instructions can be found on `dis` package's [docs](https://docs.python.org/3/library/dis.html#python-bytecode-instructions).

You probably want to start with the `<module>` code block and follow the code instructions (defining functions, classes, methods).
If the compiled program isn't super complex, you can recreate the original Python source pretty closely.
Well, probably close enough.

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
