#!/usr/bin/env bash
# strict mode for shell, makes sure all commands exit with 0 and that all variables are defined
# from my experience i particularly recommend you use this as often as possible!
set -e
set -u
# for debugging will print every line out before executing it
#set -x
#to turn on the extended pattern matching features
shopt -s extglob

alias qsub="qsub -cwd -b y -u nikolas"

function usage() {
    echo "syntax: $0"
    echo " -m : method [platinum|wallace|kmeans]"
    echo " -s : snp file or snp name if file does not exist"
    echo " -i : input dir"
    echo " -h : prints this message"
    exit 1
}


KIR_BIN=~nikolas/Projects/KIR/bin

function platinum() {
    INFILE=$1
    OUTFILE=$2
    chmod u+rx $KIR_BIN/snp-caller/platinum-call.sh
    qsub -N "platinum-$snp" -o ${OUTFILE%.*}.out -e ${OUTFILE%.*}.err $KIR_BIN/snp-caller/platinum-call.sh -i $INFILE -o $OUTFILE
}

function wallace() {
    INFILE=$1
    OUTFILE=$2
    chmod u+rx $KIR_BIN/snp-caller/wallace-call.R
    qsub -N "wallace-$snp" -o ${OUTFILE%.*}.out -e ${OUTFILE%.*}.err $KIR_BIN/snp-caller/wallace-call.R --in.file $INFILE --out.file $OUTFILE --ncopies 3
}

function kmeans() {
    INFILE=$1
    OUTFILE=$2
    chmod u+rx $KIR_BIN/snp-caller/kmeans-call.R
    qsub -N "kmeans-$snp" -o ${OUTFILE%.*}.out -e ${OUTFILE%.*}.err $KIR_BIN/snp-caller/kmeans-call.R --in.file $INFILE --out.file $OUTFILE
}

function main() {
    METHOD=
    KIR_SNP=
    INDIR=
    OUTDIR=
    # parse the args, unfortunately getopts only accepts short arguments
    # of the style -b not --blah
    while getopts "m:s:i:h" optionName
    do
        case "$optionName" in
        m) METHOD=$OPTARG;;
        s) KIR_SNP=$OPTARG;;
        i) INDIR=$OPTARG;;
        ?) usage 0;;
        esac
    done
    OUTDIR=$INDIR/$METHOD
    mkdir -p $OUTDIR
    # checks if KIR_SNP is an existing file
    if [ -e "$KIR_SNP" ]
    then
        KIR_SNP=`tail -n +2 $KIR_SNP | cut -d, -f1 `
    fi
    for snp in $KIR_SNP
    do
        echo $METHOD $INDIR/$snp.csv $OUTDIR/$snp.csv
        $METHOD $INDIR/$snp.csv $OUTDIR/$snp.csv
    done
}

### MAIN
main $*
