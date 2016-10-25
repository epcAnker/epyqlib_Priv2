#!/usr/bin/env python3

import argparse
import epyqlib.device
try:
    import git
except ImportError as e:
    raise ImportError('Package gitpython expected but not found') from e
import json
import os
import pip
import shutil
import stat
import sys
import tempfile
import zipfile


# TODO: CAMPid 0238493420143087667542054268097120437916848
# http://stackoverflow.com/a/21263493/228539
def del_rw(action, name, exc):
    os.chmod(name, stat.S_IWRITE)
    if os.path.isdir(name):
        os.rmdir(name)
    else:
        os.remove(name)


def collect(devices, output_directory):
    with tempfile.TemporaryDirectory() as checkout_dir:
        os.makedirs(output_directory, exist_ok=True)

        for name, values in devices.items():
            dir = os.path.join(checkout_dir, name)
            print('  Handling {}'.format(name))
            print('    Cloning {}'.format(values['repository']))
            repo = git.Repo.clone_from(values['repository'], dir)
            repo.git.checkout(values['branch'])

            device_path = os.path.join(dir, values['file'])
            print('    Loading {}'.format(values['file']))
            device = epyqlib.device.Device(file=device_path,
                                           only_for_files=True)
            device_dir = os.path.dirname(device_path)
            device_file_name = os.path.basename(device_path)
            referenced_files = [
                device_file_name,
                *device.referenced_files
            ]

            zip_file_name = name + '.epz'
            zip_path = os.path.join(output_directory, zip_file_name)
            print('    Writing {}'.format(zip_file_name))

            with zipfile.ZipFile(file=zip_path, mode='w') as zip:
                for device_path in referenced_files:
                    filename = os.path.join(device_dir, device_path)
                    zip.write(filename=filename,
                              arcname=os.path.relpath(filename, start=device_dir)
                              )

            # http://bugs.python.org/issue26660
            shutil.rmtree(dir, onerror=del_rw)


class LoadJsonFiles(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is None:
            setattr(namespace, self.dest, [])

        for value in values:
            getattr(namespace, self.dest).append(
                (value.name, json.loads(value.read()))
            )


def parse_args(args):
    parser =  argparse.ArgumentParser()
    parser.add_argument('--device-file', '-d', type=argparse.FileType('r'),
                        action=LoadJsonFiles, dest='device_files', nargs='+',
                        required=True)
    parser.add_argument('--output-directory', '-o', default=os.getcwd())

    return parser.parse_args(args)


def main(args=None, device_files=None, output_directory=None):
    if args is None:
        args = sys.argv[1:]

    if device_files is not None:
        for device in device_files:
            args.extend(['-d', device])

    if output_directory is not None:
        args.extend(['-o', output_directory])

    args = parse_args(args=args)

    for name, devices in args.device_files:
        print('Processing {}'.format(name))
        collect(devices=devices, output_directory=args.output_directory)


if __name__ == '__main__':
    os.environ['PATH'] = os.pathsep.join((
        os.environ['PATH'],
        os.path.join('c:/', 'Program Files', 'Git', 'bin')
    ))

    sys.exit(main())
