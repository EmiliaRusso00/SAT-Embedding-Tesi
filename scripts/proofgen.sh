#!/bin/bash

cd ~/Documents/glucose/simp || exit

./glucose_static -certified -certified-output=proof.txt \
  ~/Documents/SAT-Embedding-Tesi/outputs/27/reduced/exp_27_reduced.cnf \
  result.txt

mv proof.txt  ~/Documents/SAT-Embedding-Tesi/outputs/27/reduced/proof_27_reduced.txt
mv result.txt ~/Documents/SAT-Embedding-Tesi/outputs/27/reduced/result_27_reduced.txt