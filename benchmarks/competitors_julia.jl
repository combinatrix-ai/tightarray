using Statistics
const sink = Ref{Any}()
@noinline function run_batch(f, n)
    for _ in 1:n
        sink[] = f()
    end
end
function measure(f)
    f(); run_batch(f, 1)
    loops=1
    while loops<65536 && (@elapsed run_batch(f,loops))<0.003
        loops*=2
    end
    samples=[(@elapsed run_batch(f,loops))*1e9/loops for _ in 1:5]
    GC.gc()
    allocated=@allocated f()
    median(samples), allocated
end
raw=read(ARGS[1]); n=length(raw)
@assert all(x->x<=1,raw)
indices=parse.(Int,readlines(ARGS[2])) .+ 1
open(ARGS[3],"w") do io
    println(io,"julia,library,n,method,ns,retained_bytes,allocated_bytes")
    for (name,a) in [("Julia-BitArray",BitArray(raw .!= 0)),("Julia-UInt8",copy(raw))]
        @assert Int.(a)==Int.(raw)
        operations=[("copy",()->copy(a)),("count",()->(a isa BitArray ? count(a) : count(==(0x01),a))),("sum",()->sum(a)),("gather-256",()->a[indices])]
        @assert operations[2][2]()==count(==(1),raw)
        @assert operations[3][2]()==sum(raw)
        @assert operations[4][2]()==raw[indices]
        for (method,f) in operations
            ns,allocated=measure(f)
            println(io,"$(VERSION),$name,$n,$method,$ns,$(Base.summarysize(a)),$allocated")
        end
    end
end
