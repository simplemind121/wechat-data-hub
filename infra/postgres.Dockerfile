FROM postgres:17.6-alpine@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94 AS vector-build
USER root
ADD --checksum=sha256:83d673c3b287cddbf3879f86215f043f2c2b56c69d37b2a77504910db1ed6e56 https://github.com/pgvector/pgvector/archive/f37c13f68b57d2c3472b2214fbcff699d6d34876.tar.gz /tmp/vector.tar.gz
RUN apk add --no-cache gcc make musl-dev && \
    mkdir /tmp/vector && tar -xzf /tmp/vector.tar.gz -C /tmp/vector --strip-components=1 && \
    cd /tmp/vector && make -j2 OPTFLAGS="" with_llvm=no && make install OPTFLAGS="" with_llvm=no
FROM postgres:17.6-alpine@sha256:ef257d85f76e48da1c64832459b59fcaba1a4dac97bf5d7450c77753542eee94
COPY --from=vector-build /usr/local/lib/postgresql/vector.so /usr/local/lib/postgresql/vector.so
COPY --chmod=0644 --from=vector-build /usr/local/share/postgresql/extension/vector* /usr/local/share/postgresql/extension/
