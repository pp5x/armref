#!/usr/bin/env sh

mkdir -p ref

wget -nc -O ref/sysreg.tar.gz 'https://developer.arm.com/-/cdn-downloads/permalink/Exploration-Tools-Arm-Architecture-System-Registers/SysReg/SysReg_xml_A_profile-2026-09.tar.gz'
wget -nc -O ref/isa_a64.tar.gz 'https://developer.arm.com/-/cdn-downloads/permalink/Exploration-Tools-A64-ISA/ISA_A64/ISA_A64_xml_A_profile-2026-09.tar.gz'

for archive in sysreg isa_a64; do
    (
        mkdir ref/${archive}
        cd ref/${archive}

        tar xaf ../${archive}.tar.gz
    )
done
