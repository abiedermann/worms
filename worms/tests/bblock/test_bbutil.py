import numpy as np
from worms.bblock.bbutil import make_connections_array

def test_make_connections_array1():
   entries = [
       {'direction': 'N', 'chain': 1, 'residues': '1,:1'},
       {'direction': 'C', 'chain': 1, 'residues': '1,-7:'},
       {'direction': 'N', 'chain': 2, 'residues': '2,:2'},
       {'direction': 'C', 'chain': 2, 'residues': '2,-2:'},
       {'direction': 'N', 'chain': 3, 'residues': '3,:3'},
       {'direction': 'C', 'chain': 3, 'residues': '3,-3:'},
   ]  # yapf: disable
   chain_bounds = [(0, 9), (9, 18), (18, 27)]
   a = make_connections_array(entries, chain_bounds)
   b = np.array([
      [0, 3, 0, -1, -1, -1, -1, -1, -1],
      [1, 9, 2, 3, 4, 5, 6, 7, 8],
      [0, 4, 9, 10, -1, -1, -1, -1, -1],
      [1, 4, 16, 17, -1, -1, -1, -1, -1],
      [0, 5, 18, 19, 20, -1, -1, -1, -1],
      [1, 5, 24, 25, 26, -1, -1, -1, -1],
   ])
   assert np.all(a == b)

def test_make_connections_merge():
   entries = [
       {'direction': 'N', 'chain': 1, 'residues': [3,4]},
       {'direction': 'N', 'chain': 1, 'residues': [4,5]},
       # {'direction': 'N', 'chain': 1, 'residues': '1,-7:'},
   ]  # yapf: disable
   chain_bounds = [(0, 10), (10, 20), (20, 30)]
   a = make_connections_array(entries, chain_bounds)
   for _ in a:
      print(_)
   b = np.array([
      [0, 3, 0, -1, -1, -1, -1, -1, -1],
      [1, 9, 2, 3, 4, 5, 6, 7, 8],
      [0, 4, 9, 10, -1, -1, -1, -1, -1],
      [1, 4, 16, 17, -1, -1, -1, -1, -1],
      [0, 5, 18, 19, 20, -1, -1, -1, -1],
      [1, 5, 24, 25, 26, -1, -1, -1, -1],
   ])
   assert np.all(a == b)

if __name__ == '__main__':
   test_make_connections_merge()
