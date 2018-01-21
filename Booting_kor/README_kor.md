# 커널 부팅 과정

이 장은 리눅스 커널 부팅과정에 대해 설명한다. 이 장에서
커널 부팅이 어떻게 일어나는지 모든과정을 보게 될 것이다.

* [부트로더에서 커널까지](linux-bootstrap-1.md) - 컴퓨터의 전원이 들어온 순간부터 커널의 첫 명령어가 실행되기 까지
* [커널 준비코드의 첫 단계](linux-bootstrap-2.md) - 커널 준비코드의 첫 단계. Heap 초기화, EDD, IST등의 parameter 를 query하는 것 
* [Video mode 초기화와 protected mode로 전환](linux-bootstrap-3.md) - 커널 준비 코드에서의 Video mode 초기화와 protected mode로의 전환.
* [64-bit mode로의 전환](linux-bootstrap-4.md) - 64-bit mode 전환 준비과정 및 64-bit mode 전환.
* [커널 Decompression](linux-bootstrap-5.md) - 커널을 압축해제하기위한 준비 과정과 direct decompression 과정.
* [커널 random address randomization](linux-bootstrap-6.md) - 커널이 로드되는 메모리의 randomization 과정.
