"""TODO: Summary

Attributes:
    numcom (int): Description
    numline (int): Description
    numray (int): Description
    numseg (int): Description
    numvec (int): Description
    showme_state (TYPE): Description
"""
import tempfile
import numpy as np
from collections import defaultdict
import homog
from worms import util
from logging import info
from functools import singledispatch

try:
   from pymol import cmd
   from pymol import cgo
except ImportError:
   info("pymol not available!")

try:
   from pyrosetta.rosetta.core.pose import Pose
except ImportError:
   from unittest.mock import MagicMock

   Pose = MagicMock()

_atom_record_format = (
   "ATOM  {atomi:5d} {atomn:^4}{idx:^1}{resn:3s} {chain:1}{resi:4d}{insert:1s}   "
   "{x:8.3f}{y:8.3f}{z:8.3f}{occ:6.2f}{b:6.2f}\n")

def format_atom(
      atomi=0,
      atomn="ATOM",
      idx=" ",
      resn="RES",
      chain="A",
      resi=0,
      insert=" ",
      x=0,
      y=0,
      z=0,
      occ=0,
      b=0,
):
   return _atom_record_format.format(**locals())

def is_rosetta_pose(to_show):
   return isinstance(to_show, Pose)

def pymol_load_pose(pose, name):
   from pymol import cmd

   tmpdir = tempfile.mkdtemp()
   fname = tmpdir + "/" + name + ".pdb"
   pose.dump_pdb(fname)
   cmd.load(fname)

def pymol_xform(name, xform):
   from pymol import cmd

   assert name in cmd.get_object_list()
   cmd.transform_object(name, xform.flatten())

@singledispatch
def pymol_load(to_show, state=None, name=None, **kw):
   raise NotImplementedError("pymol_load: don't know how to show " + str(type(to_show)))

@pymol_load.register(Pose)
def _(to_show, state=None, name=None, **kw):
   name = name or "rif_thing"
   state["seenit"][name] += 1
   name += "_%i" % state["seenit"][name]
   pymol_load_pose(to_show, name)
   state["last_obj"] = name
   return state

@pymol_load.register(dict)
def _(to_show, state=None, name=None, **kw):
   assert "pose" in to_show
   state = pymol_load(to_show["pose"], state)
   pymol_xform(to_show["position"], state["last_obj"])
   return state

@pymol_load.register(list)
def _(to_show, state=None, name=None, **kw):
   for t in to_show:
      state = pymol_load(t, state)
   return state

@pymol_load.register(np.ndarray)
def _(to_show, state=None, name=None, **kw):
   name = name or "worms_thing"
   state["seenit"][name] += 1
   name += "_%i" % state["seenit"][name]
   from pymol import cmd

   tmpdir = tempfile.mkdtemp()
   fname = tmpdir + "/" + name + ".pdb"
   assert to_show.shape[-2:] == (3, 4)
   with open(fname, "w") as out:
      for i, a1 in enumerate(to_show.reshape(-1, 3, 4)):
         for j, a in enumerate(a1):
            line = format_atom(
               atomi=3 * i + j,
               resn="GLY",
               resi=i,
               atomn=(" N  ", " CA ", " C  ")[j],
               x=a[0],
               y=a[1],
               z=a[2],
            )
            out.write(line)
   cmd.load(fname)
   return state

# def pymol_load_OLD(to_show, state=None, name=None, **kw):
#     """TODO: Summary

#     Args:
#         to_show (TYPE): Description
#         state (None, optional): Description
#         name (None, optional): Description
#         kw: passthru args
#     Returns:
#         TYPE: Description

#     Raises:
#         NotImplementedError: Description
#     """
#     if isinstance(to_show, list):
#         for t in to_show:
#             state = pymol_load(t, state)
#     elif isinstance(to_show, dict):
#         assert 'pose' in to_show
#         state = pymol_load(to_show['pose'], state)
#         pymol_xform(to_show['position'], state['last_obj'])
#     elif is_rosetta_pose(to_show):
#         name = name or 'rif_thing'
#         state['seenit'][name] += 1
#         name += '_%i' % state['seenit'][name]
#         pymol_load_pose(to_show, name)
#         state['last_obj'] = name
#     elif isinstance(to_show, np.ndarray):

#         raise NotImplementedError

#         showsegment(to_show, [0, 0, 0], **kw)
#     else:
#         raise NotImplementedError(
#             "don't know how to show " + str(type(to_show)))
#     return state

showme_state = dict(launched=0, seenit=defaultdict(lambda: -1))

def showme_pymol(what, headless=False, block=False, **kw):
   """TODO: Summary

    Args:
        what (TYPE): Description
        headless (bool, optional): Description
        block (bool, optional): Description
        kw: passthru args
    Returns:
        TYPE: Description
    """
   import pymol

   pymol.pymol_argv = ["pymol"]
   if headless:
      pymol.pymol_argv = ["pymol", "-c"]
   if not showme_state["launched"]:
      pymol.finish_launching()
      showme_state["launched"] = 1
   from pymol import cmd

   r = pymol_load(what, showme_state, **kw)
   # cmd.set('internal_gui_width', '20')
   import time

   while block:
      time.sleep(1)
   return r

def showme(*args, how="pymol", **kw):
   """TODO: Summary

    Args:
        args: passthru args
        how (str, optional): Description
        kw: passthru args
    Returns:
        TYPE: Description

    Raises:
        NotImplementedError: Description
    """
   if how == "pymol":
      return showme_pymol(*args, **kw)
   else:
      raise NotImplementedError('showme how="%s" not implemented' % how)

numcom = 0
numvec = 0
numray = 0
numline = 0
numseg = 0

def showcom(sel="all"):
   """TODO: Summary

    Args:
        sel (str, optional): Description
    """
   global numcom
   c = com(sel)
   print("Center of mass: ", c)
   cgo = [
      pymol.cgo.COLOR,
      1.0,
      1.0,
      1.0,
      cgo.SPHERE,
      c[0],
      c[1],
      c[2],
      1.0,
   ]  # white sphere with 3A radius
   cmd.load_cgo(cgo, "com%i" % numcom)
   numcom += 1

def cgo_sphere(c, r=1, col=(1, 1, 1)):
   """TODO: Summary

    Args:
        c (TYPE): Description
        r (int, optional): Description
        col (tuple, optional): Description

    Returns:
        TYPE: Description
    """
   # white sphere with 3A radius
   return [cgo.COLOR, col[0], col[1], col[2], cgo.SPHERE, c[0], c[1], c[2], r]

def showsphere(c, r=1, col=(1, 1, 1), lbl=""):
   """TODO: Summary

    Args:
        c (TYPE): Description
        r (int, optional): Description
        col (tuple, optional): Description
        lbl (str, optional): Description
    """
   v = cmd.get_view()
   if not lbl:
      global numvec
      lbl = "sphere%i" % numvec
      numvec += 1
   mycgo = cgo_sphere(c=c, r=r, col=col)
   cmd.load_cgo(mycgo, lbl)
   cmd.set_view(v)

def showvecfrompoint(a, c, col=(1, 1, 1), lbl=""):
   """TODO: Summary

    Args:
        a (TYPE): Description
        c (TYPE): Description
        col (tuple, optional): Description
        lbl (str, optional): Description
    """
   if not lbl:
      global numray
      lbl = "ray%i" % numray
      numray += 1
   cmd.delete(lbl)
   v = cmd.get_view()
   OBJ = [
      cgo.BEGIN,
      cgo.LINES,
      cgo.COLOR,
      col[0],
      col[1],
      col[2],
      cgo.VERTEX,
      c[0],
      c[1],
      c[2],
      cgo.VERTEX,
      c[0] + a[0],
      c[1] + a[1],
      c[2] + a[2],
      cgo.END,
   ]
   cmd.load_cgo(OBJ, lbl)
   # cmd.load_cgo([cgo.COLOR, col[0],col[1],col[2],
   #             cgo.SPHERE,   c[0],       c[1],       c[2],    0.08,
   #             cgo.CYLINDER, c[0],       c[1],       c[2],
   #                       c[0] + a[0], c[1] + a[1], c[2] + a[2], 0.02,
   #               col[0],col[1],col[2],col[0],col[1],col[2],], lbl)
   cmd.set_view(v)

def cgo_segment(c1, c2, col=(1, 1, 1)):
   """TODO: Summary

    Args:
        c1 (TYPE): Description
        c2 (TYPE): Description
        col (tuple, optional): Description

    Returns:
        TYPE: Description
    """
   OBJ = [
      cgo.BEGIN,
      cgo.LINES,
      cgo.COLOR,
      col[0],
      col[1],
      col[2],
      cgo.VERTEX,
      c1[0],
      c1[1],
      c1[2],
      cgo.VERTEX,
      c2[0],
      c2[1],
      c2[2],
      cgo.END,
   ]
   # cmd.load_cgo([cgo.COLOR, col[0],col[1],col[2],
   #             cgo.CYLINDER, c1[0],     c1[1],     c1[2],
   #                           c2[0],     c2[1],     c2[2], 0.02,
   #               col[0],col[1],col[2],col[0],col[1],col[2],], lbl)
   return OBJ

def showsegment(c1, c2, col=(1, 1, 1), lbl=""):
   """TODO: Summary

    Args:
        c1 (TYPE): Description
        c2 (TYPE): Description
        col (tuple, optional): Description
        lbl (str, optional): Description
    """
   if not lbl:
      global numseg
      lbl = "seg%i" % numseg
      numseg += 1
   cmd.delete(lbl)
   v = cmd.get_view()
   cmd.load_cgo(cgo_segment(c1=c1, c2=c2, col=col), lbl)
   # cmd.load_cgo([cgo.COLOR, col[0],col[1],col[2],
   #             cgo.CYLINDER, c1[0],     c1[1],     c1[2],
   #                           c2[0],     c2[1],     c2[2], 0.02,
   #               col[0],col[1],col[2],col[0],col[1],col[2],], lbl)
   cmd.set_view(v)

def cgo_cyl(c1, c2, r, col=(1, 1, 1), col2=None):
   """TODO: Summary

    Args:
        c1 (TYPE): Description
        c2 (TYPE): Description
        r (TYPE): Description
        col (tuple, optional): Description
        col2 (None, optional): Description

    Returns:
        TYPE: Description
    """
   if not col2:
      col2 = col
   return [  # cgo.COLOR, col[0],col[1],col[2],
      cgo.CYLINDER,
      c1[0],
      c1[1],
      c1[2],
      c2[0],
      c2[1],
      c2[2],
      r,
      col[0],
      col[1],
      col[2],
      col2[0],
      col2[1],
      col2[2],
   ]

def showcyl(c1, c2, r, col=(1, 1, 1), col2=None, lbl=""):
   """TODO: Summary

    Args:
        c1 (TYPE): Description
        c2 (TYPE): Description
        r (TYPE): Description
        col (tuple, optional): Description
        col2 (None, optional): Description
        lbl (str, optional): Description
    """
   if not lbl:
      global numseg
      lbl = "seg%i" % numseg
      numseg += 1
   cmd.delete(lbl)
   v = cmd.get_view()
   cmd.load_cgo(cgo_cyl(c1=c1, c2=c2, r=r, col=col, col2=col2), lbl)
   cmd.set_view(v)

def showline(a, c, col=(1, 1, 1), lbl=""):
   """TODO: Summary

    Args:
        a (TYPE): Description
        c (TYPE): Description
        col (tuple, optional): Description
        lbl (str, optional): Description
    """
   if not lbl:
      global numline
      lbl = "line%i" % numline
      numline += 1
   cmd.delete(lbl)
   v = cmd.get_view()
   OBJ = [
      cgo.BEGIN,
      cgo.LINES,
      cgo.COLOR,
      col[0],
      col[1],
      col[2],
      cgo.VERTEX,
      c[0] - a[0],
      c[1] - a[1],
      c[2] - a[2],
      cgo.VERTEX,
      c[0] + a[0],
      c[1] + a[1],
      c[2] + a[2],
      cgo.END,
   ]
   cmd.load_cgo(OBJ, lbl)
   cmd.set_view(v)

def cgo_lineabs(a, c, col=(1, 1, 1)):
   """TODO: Summary

    Args:
        a (TYPE): Description
        c (TYPE): Description
        col (tuple, optional): Description

    Returns:
        TYPE: Description
    """
   return [
      cgo.BEGIN,
      cgo.LINES,
      cgo.COLOR,
      col[0],
      col[1],
      col[2],
      cgo.VERTEX,
      c[0],
      c[1],
      c[2],
      cgo.VERTEX,
      a[0],
      a[1],
      a[2],
      cgo.END,
   ]

def showlineabs(a, c, col=(1, 1, 1), lbl=""):
   """TODO: Summary

    Args:
        a (TYPE): Description
        c (TYPE): Description
        col (tuple, optional): Description
        lbl (str, optional): Description
    """
   if not lbl:
      global numline
      lbl = "line%i" % numline
      numline += 1
   cmd.delete(lbl)
   v = cmd.get_view()
   cgo = cgo_lineabs(a, c, col)
   cmd.load_cgo(cgo, lbl)
   cmd.set_view(v)

def show_with_axis(worms, idx=0):
   """TODO: Summary

    Args:
        worms (TYPE): Description
        idx (int, optional): Description
    """
   pose = worms.pose(idx, align=0, end=1)
   x_from = worms.positions[idx][worms.criteria.from_seg]
   x_to = worms.positions[idx][worms.criteria.to_seg]
   x = x_to @ np.linalg.inv(x_from)
   axis, ang, cen = homog.axis_ang_cen_of(x)
   np.set_printoptions(precision=20)
   print(x)
   print(axis)
   print(ang)
   print(cen)
   axis *= 100
   showme(pose, name="unit")
   util.xform_pose(x, pose)
   showme(pose, name="sym1")
   util.xform_pose(x, pose)
   showme(pose, name="sym2")
   showline(axis, cen)
   showsphere(cen)

def show_with_z_axes(worms, idx=0, only_connected=0, **kw):
   """TODO: Summary

    Args:
        worms (TYPE): Description
        idx (int, optional): Description
        only_connected (int, optional): Description
        kw: passthru args    """
   pose = worms.pose(idx, align=0, end=1, only_connected=only_connected, **kw)
   x_from = worms.positions[idx][worms.criteria.from_seg]
   x_to = worms.positions[idx][worms.criteria.to_seg]
   cen1 = x_from[..., :, 3]
   cen2 = x_to[..., :, 3]
   axis1 = x_from[..., :, 2] * 100
   axis2 = x_to[..., :, 2] * 100
   showme(pose)
   import pymol

   pymol.finish_launching()
   showline(axis1, cen1)
   showsphere(cen1)
   showline(axis2, cen2)
   showsphere(cen2)
