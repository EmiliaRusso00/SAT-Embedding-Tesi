#!/bin/bash

cd ~/Documents/glucose/simp || exit

./glucose_static -certified -certified-output=proof.txt \
  ~/Documents/SAT-Embedding-Tesi/outputs/13/reduced/exp_13_reduced.cnf \
  result.txt

mv proof.txt  ~/Documents/SAT-Embedding-Tesi/outputs/13/reduced/proof_13_reduced.txt
mv result.txt ~/Documents/SAT-Embedding-Tesi/outputs/13/reduced/result_13_reduced.txt