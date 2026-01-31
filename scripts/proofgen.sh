#!/bin/bash

cd ~/Documents/glucose/simp || exit

./glucose_static -certified -certified-output=proof.txt \
  ~/Documents/SAT-Embedding-Tesi/outputs/1/reduced/exp_1_reduced.cnf \
  result.txt

mv proof.txt  ~/Documents/SAT-Embedding-Tesi/outputs/1/reduced/proof_1_reduced.txt
mv result.txt ~/Documents/SAT-Embedding-Tesi/outputs/1/reduced/result_1_reduced.txt