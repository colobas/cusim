# Copyright (c) 2020 Jisang Yoon
# All rights reserved.
#
# This source code is licensed under the Apache 2.0 license found in the
# LICENSE file in the root directory of this source tree.

# Adapted from https://github.com/rmcgibbo/npcuda-example and
# https://github.com/cupy/cupy/blob/master/cupy_setup_build.py
# pylint: disable=fixme,access-member-before-definition
# pylint: disable=attribute-defined-outside-init,arguments-differ
import logging
import os
import sys

try:
    import numpy.distutils
except ImportError:
    pass

from distutils import ccompiler, errors, unixccompiler
from setuptools.command.build_ext import build_ext as setuptools_build_ext

HALF_PRECISION = False

def find_in_path(name, path):
  "Find a file in a search path"
  # adapted fom http://code.activestate.com/
  # recipes/52224-find-a-file-given-a-search-path/
  for _dir in path.split(os.pathsep):
    binpath = os.path.join(_dir, name)
    if os.path.exists(binpath):
      return os.path.abspath(binpath)
  return None

# reference: https://arnon.dk/
# matching-sm-architectures-arch-and-gencode-for-various-nvidia-cards/
def get_cuda_sm_list(cuda_ver):
  if "CUDA_SM_LIST" in os.environ:
    sm_list = os.environ["CUDA_SM_LIST"].split(",")
  else:
    sm_list = ["30", "52", "60", "61", "70", "75", "80", "86"]
    if cuda_ver >= 110:
      filter_list = ["30"]
      if cuda_ver == 110:
        filter_list += ["86"]
    else:
      filter_list = ["80", "86"]
      if cuda_ver < 100:
        filter_list += ["75"]
      if cuda_ver < 90:
        filter_list += ["70"]
      if cuda_ver < 80:
        filter_list += ["60", "61"]
    sm_list = [sm for sm in sm_list if sm not in filter_list]
  return sm_list


def get_cuda_compute(cuda_ver):
    if "CUDA_COMPUTE" in os.environ:
        compute = os.environ["CUDA_COMPUTE"]
    else:
        if 70 <= cuda_ver < 80:
            compute = "52"
        elif 80 <= cuda_ver < 90:
            compute = "61"
        elif 90 <= cuda_ver < 100:
            compute = "70"
        elif 100 <= cuda_ver < 110:
            compute = "75"
        elif cuda_ver == 110:
            compute = "80"
        elif 111 <= cuda_ver < 115:
            compute = "86"
        elif 115 <= cuda_ver < 120:
            compute = "89"
        elif 120 <= cuda_ver <= 128:
            compute = "90"
        else:
            # Fallback for versions outside known ranges
            compute = "90"  # Default to newest supported
    return compute


def get_cuda_arch(cuda_ver):
    if "CUDA_ARCH" in os.environ:
        arch = os.environ["CUDA_ARCH"]
    else:
        if 70 <= cuda_ver < 92:
            arch = "30"
        elif 92 <= cuda_ver < 110:
            arch = "50"
        elif cuda_ver == 110:
            arch = "52"
        elif 111 <= cuda_ver < 120:
            arch = "80"
        elif 120 <= cuda_ver <= 128:
            arch = "90"
        else:
            # Fallback for versions outside known ranges
            arch = "90"  # Default to newest supported
    return arch

def locate_cuda():
  """Locate the CUDA environment on the system
  If a valid cuda installation is found
  this returns a dict with keys 'home', 'nvcc', 'include',
  and 'lib64' and values giving the absolute path to each directory.
  Starts by looking for the CUDAHOME env variable.
  If not found, everything is based on finding
  'nvcc' in the PATH.
  If nvcc can't be found, this returns None
  """
  nvcc_bin = 'nvcc'
  if sys.platform.startswith("win"):
    nvcc_bin = 'nvcc.exe'

  # check env variables CUDA_HOME, CUDAHOME, CUDA_PATH.
  found = False
  for env_name in ['CUDA_PATH', 'CUDAHOME', 'CUDA_HOME']:
    if env_name not in os.environ:
      continue
    found = True
    home = os.environ[env_name]
    nvcc = os.path.join(home, 'bin', nvcc_bin)
    break
  if not found:
    # otherwise, search the PATH for NVCC
    nvcc = find_in_path(nvcc_bin, os.environ['PATH'])
    if nvcc is None:
      logging.warning('The nvcc binary could not be located in your '
              '$PATH. Either add it to '
              'your path, or set $CUDA_HOME to enable CUDA extensions')
      return None
    home = os.path.dirname(os.path.dirname(nvcc))
  cudaconfig = {'home': home,
                'nvcc': nvcc,
                'include': os.path.join(home, 'include'),
                'lib64':   os.path.join(home, 'lib64')}
  try:
    cuda_ver = os.path.basename(os.path.realpath(home)).split("-")[1].split(".")
  except:
    cuda_ver = os.path.basename(os.path.realpath(home)).split(".")
  major, minor = int(cuda_ver[0]), int(cuda_ver[1])
  cuda_ver = 10 * major + minor
  assert cuda_ver >= 70, f"too low cuda ver {major}.{minor}"
  print(f"cuda_ver: {major}.{minor}")
  arch = get_cuda_arch(cuda_ver)
  sm_list = get_cuda_sm_list(cuda_ver)
  compute = get_cuda_compute(cuda_ver)
  post_args = [f"-arch=sm_{arch}"] + \
    [f"-gencode=arch=compute_{sm},code=sm_{sm}" for sm in sm_list] + \
    [f"-gencode=arch=compute_{compute},code=compute_{compute}",
     "--ptxas-options=-v", "-O2"]
  print(f"nvcc post args: {post_args}")
  if HALF_PRECISION:
    post_args = [flag for flag in post_args if "52" not in flag]

  if sys.platform == "win32":
    cudaconfig['lib64'] = os.path.join(home, 'lib', 'x64')
    post_args += ['-Xcompiler', '/MD', '-std=c++14',  "-Xcompiler", "/openmp"]
    if HALF_PRECISION:
      post_args += ["-Xcompiler", "/D HALF_PRECISION"]
  else:
    post_args += ['-c', '--compiler-options', "'-fPIC'",
                  "--compiler-options", "'-std=c++14'"]
    if HALF_PRECISION:
      post_args += ["--compiler-options", "'-D HALF_PRECISION'"]
  for k, val in cudaconfig.items():
    if not os.path.exists(val):
      logging.warning('The CUDA %s path could not be located in %s', k, val)
      return None

  cudaconfig['post_args'] = post_args
  return cudaconfig


# This code to build .cu extensions with nvcc is taken from cupy:
# https://github.com/cupy/cupy/blob/master/cupy_setup_build.py
class _UnixCCompiler(unixccompiler.UnixCCompiler):
  src_extensions = list(unixccompiler.UnixCCompiler.src_extensions)
  src_extensions.append('.cu')

  def _compile(self, obj, src, ext, cc_args, extra_postargs, pp_opts):
    # For sources other than CUDA C ones, just call the super class method.
    if os.path.splitext(src)[1] != '.cu':
      return unixccompiler.UnixCCompiler._compile(
        self, obj, src, ext, cc_args, extra_postargs, pp_opts)

    # For CUDA C source files, compile them with NVCC.
    _compiler_so = self.compiler_so
    try:
      nvcc_path = CUDA['nvcc']
      post_args = CUDA['post_args']
      # TODO? base_opts = build.get_compiler_base_options()
      self.set_executable('compiler_so', nvcc_path)

      return unixccompiler.UnixCCompiler._compile(
        self, obj, src, ext, cc_args, post_args, pp_opts)
    finally:
      self.compiler_so = _compiler_so


class CudaBuildExt(setuptools_build_ext):
  """Custom `build_ext` command to include CUDA C source files."""

  def run(self):
    if CUDA is not None:
      def wrap_new_compiler(func):
        def _wrap_new_compiler(*args, **kwargs):
          try:
            return func(*args, **kwargs)
          except errors.DistutilsPlatformError:
            if sys.platform != 'win32':
              CCompiler = _UnixCCompiler
            else:
              CCompiler = _MSVCCompiler
            return CCompiler(
              None, kwargs['dry_run'], kwargs['force'])
        return _wrap_new_compiler
      ccompiler.new_compiler = wrap_new_compiler(ccompiler.new_compiler)
      # Intentionally causes DistutilsPlatformError in
      # ccompiler.new_compiler() function to hook.
      self.compiler = 'nvidia'

    setuptools_build_ext.run(self)


CUDA = locate_cuda()
assert CUDA is not None
BUILDEXT = CudaBuildExt if CUDA else setuptools_build_ext
