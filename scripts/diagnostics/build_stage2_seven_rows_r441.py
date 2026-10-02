"""Expand Stage2's sparse attribute refresh to seven complete rows."""
import hashlib
import build_stage2_runtime_hdma6_r260 as prior
from build_stage5_dead_pointer_moves_r435 import ROOT, guard

BASE=ROOT/'tmp/room03-animation-envelope-r440/candidate.gb'
SHA='dcb4f553fdf03c7631a12cdfe64a990b96476bc8b69d2663c9cf4b7ab973c623'
OUT=ROOT/'tmp/stage2-seven-rows-r441'


def patches():
    runtime=prior.build_runtime().replace(bytes.fromhex('F0 A5'),bytes.fromhex('F0 01'))
    publisher=prior.build_publisher().replace(bytes.fromhex('F0 A5'),bytes.fromhex('F0 01'))
    assert runtime.count(bytes.fromhex('F0 E0 FE 12'))==1
    assert publisher.count(bytes.fromhex('3E 8B E0 55'))==1
    return [
        (prior.bank_offset(prior.BANK,prior.SPECIAL_BLOB),runtime,
         runtime.replace(bytes.fromhex('F0 E0 FE 12'),bytes.fromhex('F0 E0 FE 11'))),
        (prior.bank_offset(prior.BANK,prior.PUBLISH_ENTRY),publisher,
         publisher.replace(bytes.fromhex('3E 8B E0 55'),bytes.fromhex('3E 8D E0 55')))]


def build(source):
    if hashlib.sha256(source).hexdigest()!=SHA: raise ValueError('requires exact r440')
    result=bytearray(source)
    for offset,old,new in patches():
        assert source[offset:offset+len(old)]==old
        result[offset:offset+len(old)]=new
    guard.update_checksums(result)
    return bytes(result)


if __name__=='__main__':
    result=build(BASE.read_bytes())
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=result: raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    print(hashlib.sha256(result).hexdigest())
