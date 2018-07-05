"""TODO: Summary
"""
import os
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools as it
import logging
from logging import info, warning, error
from random import shuffle

import numpy as np
from tqdm import tqdm

from worms import util
from worms.bblock import BBlock, _BBlock

logging.basicConfig(level=logging.INFO)
import _pickle as pickle

try:
    # god, I'm so tired of this crap....
    from pyrosetta import pose_from_file
    from pyrosetta.rosetta.core.scoring.dssp import Dssp
    HAVE_PYROSETTA = True
except ImportError:
    HAVE_PYROSETTA = False


def flatten_path(pdbfile):
    """TODO: Summary

    Args:
        pdbfile (TYPE): Description

    Returns:
        TYPE: Description
    """
    if isinstance(pdbfile, bytes):
        pdbfile = str(pdbfile, 'utf-8')
    return pdbfile.replace(os.sep, '__') + '.pickle'


class SpliceDB:
    """"""

    def __init__(self, cachedir=None):
        if cachedir is None:
            if 'HOME' in os.environ:
                cachedir = os.environ['HOME'] + os.sep + '.worms/cache'
            else:
                cachedir = '.worms/cache'
        self.cachedir = os.path.join(cachedir, 'splices')
        self.cache = dict()
        self.dirty = set()

    def c_side_cache(self, params, pdbfile):
        if isinstance(pdbfile, str):
            pdbfile = pdbfile.encode()
        if (params, pdbfile) not in self.cache:
            cachefile = os.path.join(
                self.cachedir, str(hash(params)), flatten_path(pdbfile)
            )
            if os.path.exists(cachefile):
                with open(cachefile, 'rb') as f:
                    self.cache[params, pdbfile] = pickle.load(f)
            else:
                self.cache[params, pdbfile] = dict()
        return self.cache[params, pdbfile]

    def add_to_c_side_cache(self, params, pdb0, pdb1, val):
        self.dirty.add((params, pdb0))
        self.cache[(params, pdb0)][pdb1] = val

    def sync_to_disk(self):
        for i in range(10):
            for params, pdbfile in list(self.dirty):
                cachefile = os.path.join(
                    self.cachedir, str(hash(params)), flatten_path(pdbfile)
                )
                if os.path.exists(cachefile + '.lock'): continue
                if not os.path.exists(os.path.dirname(cachefile)):
                    os.makedirs(os.path.dirname(cachefile))
                with open(cachefile + '.lock', 'w'):
                    with open(cachefile, 'wb') as out:
                        data = self.cache[params, pdbfile]
                        pickle.dump(data, out)
                os.remove(cachefile + '.lock')
                self.dirty.remove((params, pdbfile))
        if len(self.dirty):
            print('warning: some caches unsaved', len(self.dirty))


def _convert_splicedb_to_dict():
    """almost the same, dicts little slower, little bigger"""
    import glob
    import _pickle
    for f in glob.glob('/home/sheffler/.worms/cache/splices/*/*.pickle'):
        print(f)
        with open(f, 'rb') as inp:
            c = _pickle.load(inp)
            for k, lst0 in c.items():
                for i, lst in enumerate(lst0):
                    if lst is not None:
                        d = {j: v for j, v in enumerate(lst) if v is not None}
                        c[k][i] = d
        with open(f, 'wb') as out:
            _pickle.dump(c, out)


class BBlockDB:
    """TODO: Summary

    Attributes:
        _alldb (list): Description
        cachedir (TYPE): Description
        dictdb (TYPE): Description
        load_poses (TYPE): Description
        lazy (TYPE): Description
        n_missing_entries (TYPE): Description
        n_new_entries (int): Description
        nprocs (int): Description
        read_new_pdbs (TYPE): Description
    """

    def __init__(
            self,
            cachedir=None,
            bakerdb_files=[],
            load_poses=False,
            nprocs=1,
            lazy=True,
            read_new_pdbs=False,
            verbosity=0,
    ):
        """TODO: Summary

        Args:
            cachedir (None, optional): Description
            bakerdb_files (list, optional): Description
            load_poses (bool, optional): Description
            nprocs (int, optional): Description
            lazy (bool, optional): Description
            read_new_pdbs (bool, optional): Description
        """
        if cachedir is None:
            if 'HOME' in os.environ:
                cachedir = os.environ['HOME'] + os.sep + '.worms/cache'
            else:
                cachedir = '.worms/cache'
        self.cachedir = str(cachedir)
        self.load_poses = load_poses
        os.makedirs(self.cachedir + '/poses', exist_ok=True)
        os.makedirs(self.cachedir + '/bblock', exist_ok=True)
        self._bblock_cache, self._poses_cache = dict(), dict()
        self.nprocs = nprocs
        self.lazy = lazy
        self.read_new_pdbs = read_new_pdbs
        self.verbosity = verbosity
        self._alldb = []
        self._holding_lock = False
        for dbfile in bakerdb_files:
            with open(dbfile) as f:
                self._alldb.extend(json.load(f))
        for entry in self._alldb:
            if 'name' not in entry:
                entry['name'] = ''
            entry['file'] = entry['file'].replace(
                '__DATADIR__',
                os.path.relpath(os.path.dirname(__file__) + '/data')
            )
        self.dictdb = {e['file']: e for e in self._alldb}
        if len(self._alldb) != len(self.dictdb):
            warning('!' * 100)
            warning(
                '!' * 23, 'DIRE WARNING: %6i duplicate pdb files in database' %
                (len(self._alldb) - len(self.dictdb)), '!' * 23
            )
            warning('!' * 100)
        info('loading %i db entries' % len(self._alldb))
        self.n_new_entries = 0
        self.n_missing_entries = len(self._alldb)
        if not self.lazy:
            self.n_new_entries, self.n_missing_entries = self.load_from_pdbs()
            if self._holding_lock: self.unlock_cachedir()
            if nprocs != 1:
                # reload because processpool cache entries not serialized back
                self.nprocs = 1
                self.load_from_pdbs()
        for i, k in enumerate(sorted(self.dictdb)):
            self._alldb[i] = self.dictdb[k]

    def lock_cachedir(self):
        assert not os.path.exists(self.cachedir + '/lock'), (
            "database is locked! if you're sure no other jobs are editing it, remove "
            + self.cachedir + "/lock"
        )
        open(self.cachedir + '/lock', 'w').close()
        assert os.path.exists(self.cachedir + '/lock')
        self._holding_lock = True

    def unlock_cachedir(self):
        os.remove(self.cachedir + '/lock')
        self._holding_lock = False

    def islocked_cachedir(self):
        return os.path.exists(self.cachedir + '/lock')

    def check_lock_cachedir(self):
        if not self._holding_lock:
            self.lock_cachedir()

    def __getitem__(self, i):
        if isinstance(i, str):
            return self._bblock_cache[i]
        else:
            return self._bblock_cache.values()[i]

    def __len__(self):
        """TODO: Summary

        Returns:
            TYPE: Description
        """
        return len(self._bblock_cache)

    def pose(self, pdbfile):
        """load pose from _bblock_cache, read from file if not in memory

        Args:
            pdbfile (TYPE): Description

        Returns:
            TYPE: Description
        """
        if isinstance(pdbfile, bytes):
            pdbfile = str(pdbfile, 'utf-8')
        if not pdbfile in self._poses_cache:
            if not self.load_cached_pose_into_memory(pdbfile):
                self._poses_cache[pdbfile] = pose_from_file(pdbfile)
        return self._poses_cache[pdbfile]

    def bblock(self, pdbfile):
        """TODO: Summary

        Args:
            pdbfile (TYPE): Description

        Returns:
            TYPE: Description
        """
        if isinstance(pdbfile, str):
            if not pdbfile in self._bblock_cache:
                if not self.load_cached_bblock_into_memory(pdbfile):
                    raise valueError('no bblock data for ', pdbfile)
            return self._bblock_cache[pdbfile]
        elif isinstance(pdbfile, list):
            return [self.bblock(f) for f in pdbfile]
        else:
            raise ValueError('bad pdbfile' + str(type(pdbfile)))

    def query(self, query, *, useclass=True, max_bblocks=150, shuffle=True):
        names = self.query_names(query, useclass=useclass)
        if len(names) > max_bblocks:
            if shuffle:
                random.shuffle(names)
            names = names[:max_bblocks]
        return [self.bblock(n) for n in names]

    def query_names(self, query, *, useclass=True):
        """
        match name, _type, _class
        if one match, use it
        if _type and _class match, check useclass option
        Het:NNCx/y require exact number or require extra

        Args:
            query (TYPE): Description
            useclass (bool, optional): Description

        Returns:
            TYPE: Description
        """
        if query.lower() == "all":
            return [db['file'] for db in self._alldb]
        query, subq = query.split(':') if query.count(':') else (query, None)
        if subq is None:
            c_hits = [db['file'] for db in self._alldb if query in db['class']]
            n_hits = [db['file'] for db in self._alldb if query == db['name']]
            t_hits = [db['file'] for db in self._alldb if query == db['type']]
            if not c_hits and not n_hits: return t_hits
            if not c_hits and not t_hits: return n_hits
            if not t_hits and not n_hits: return c_hits
            if not n_hits: return c_hits if useclass else t_hits
            assert False, 'invalid database or query'
        else:
            excon = None
            if subq.endswith('X'): excon = True
            if subq.endswith('Y'): excon = False
            hits = list()
            assert query == 'Het'
            for db in self._alldb:
                if not query in db['class']: continue
                nc = [_ for _ in db['connections'] if _['direction'] == 'C']
                nn = [_ for _ in db['connections'] if _['direction'] == 'N']
                nc, tc = len(nc), subq.count('C')
                nn, tn = len(nn), subq.count('N')
                if nc >= tc and nn >= tn:
                    if nc + nn == tc + tn and excon is not True:
                        hits.append(db['file'])
                    elif nc + nn > tc + tn and excon is not False:
                        hits.append(db['file'])
        return hits

    def load_cached_pose_into_memory(self, pdbfile):
        """TODO: Summary

        Args:
            pdbfile (TYPE): Description

        Returns:
            TYPE: Description
        """
        posefile = self.posefile(pdbfile)
        try:
            with open(posefile, 'rb') as f:
                try:
                    self._poses_cache[pdbfile] = pickle.load(f)
                    return True
                except EOFError:
                    warning('corrupt pickled pose will be replaced', posefile)
                    os.remove(posefile)
                    return False
        except FileNotFoundError:
            return False

    def bblockfile(self, pdbfile):
        """TODO: Summary"""
        return os.path.join(self.cachedir, 'bblock', flatten_path(pdbfile))

    def load_cached_bblock_into_memory(self, pdbfile):
        """TODO: Summary

        Args:
            pdbfile (TYPE): Description

        Returns:
            TYPE: Description
        """
        if not isinstance(pdbfile, str):
            success = True
            for f in pdbfile:
                success &= self.load_cached_bblock_into_memory(f)
            return success
        bblockfile = self.bblockfile(pdbfile)
        try:
            with open(bblockfile, 'rb') as f:
                bbstate = list(pickle.load(f))
                self._bblock_cache[pdbfile] = _BBlock(*bbstate)
                return True
        except FileNotFound:
            return False

    def posefile(self, pdbfile):
        """TODO: Summary"""
        return os.path.join(self.cachedir, 'poses', flatten_path(pdbfile))

    def load_from_pdbs(self):
        """Summary

       Returns:
           TYPE: Description
       """
        shuffle(self._alldb)
        if self.nprocs is 1:
            with util.InProcessExecutor() as exe:
                result = self.load_from_pdbs_inner(exe)
        else:
            with ThreadPoolExecutor(max_workers=self.nprocs) as exe:
                result = self.load_from_pdbs_inner(exe)
        new = [_[0] for _ in result if _[0]]
        missing = [_[1] for _ in result if _[1]]
        for miss in missing:
            self._alldb.remove(self.dictdb[miss])
            del self.dictdb[miss]
        return len(new), len(missing)

    def load_from_pdbs_inner(self, exe):
        """Summary

       Args:
           exe (TYPE): Description

       Returns:
           TYPE: Description
       """
        # return exe.map(self.build_pdb_data, self._alldb)
        shuffle(self._alldb)
        r = []
        kwargs = {
            'total': len(self._alldb),
            'unit': 'pdbs',
            # 'unit_scale': True,
            'leave': True
        }
        futures = [exe.submit(self.build_pdb_data, e) for e in self._alldb]
        work = as_completed(futures)
        if self.verbosity > 1:
            work = tqdm(work, 'building pdb data', **kwargs)
        for f in work:
            r.append(f.result())
        return r

    def build_pdb_data(self, entry):
        """return Nnew, Nmissing

        Args:
            entry (TYPE): Description

        Returns:
            TYPE: Description
        """
        pdbfile = entry['file']
        cachefile = os.path.join(
            self.cachedir, 'bblock', flatten_path(pdbfile)
        )
        posefile = self.posefile(pdbfile)
        if os.path.exists(cachefile):
            assert self.load_cached_bblock_into_memory(pdbfile)
            if self.load_poses:
                assert self.load_cached_pose_into_memory(pdbfile)
            return None, None  # new, missing
        elif self.read_new_pdbs:
            self.check_lock_cachedir()
            read_pdb = False
            # info('BBlockDB.build_pdb_data reading %s' % pdbfile)
            pose = self.pose(pdbfile)
            ss = Dssp(pose).get_dssp_secstruct()
            bblock = BBlock(entry, pdbfile, pose, ss)
            self._bblock_cache[pdbfile] = bblock

            with open(cachefile, 'wb') as f:
                pickle.dump(bblock._state, f)
            if not os.path.exists(posefile):
                with open(posefile, 'wb') as f:
                    pickle.dump(pose, f)
                    info('dumped _bblock_cache files for %s' % pdbfile)

            if self.load_poses:
                self._poses_cache[pdbfile] = pose
            return pdbfile, None  # new, missing
        else:
            warning('no cached data for: ' + pdbfile)
            return None, pdbfile  # new, missing
