#!/bin/bash
#per eseguire lo script ./proofgen.sh

# 1) Vai nel percorso
cd ~/Documents/glucose/simp || exit

# 2) Lista i file, in particolare glucose_static
ls -l glucose_static

# 3) Lancia Glucose con i parametri richiesti, cambia il percorso e il nome del file
./glucose_static -certified -certified-output=proof.txt \
    ~/Documents/SAT-Embedding-Tesi/outputs/20/reduced/exp_20_reduced.cnf \
    result.txt

# 4) Sposta proof nella cartella di outputs e rinominalo
mv proof.txt ~/Documents/SAT-Embedding-Tesi/outputs/20/reduced/proof_20_reduced.txt
