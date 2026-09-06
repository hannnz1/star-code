# Numeric utilities contract
Implement two independent interfaces; invalid inputs must throw IllegalArgumentException.
stats.Mean.rounded(long[]): reject null/empty. Compute the arithmetic mean rounded to the nearest long with HALF_EVEN.
Intermediate sum must not overflow even for Long.MAX_VALUE and Long.MIN_VALUE arrays. Do not mutate the input.
retry.Delay.millis(long base, int attempt, long cap): require base>=1, attempt>=0, cap>=base.
Return min(cap, base * 2^attempt), avoiding overflow and avoiding work proportional to very large attempt values.
Read tests/GateTest.java. Preserve signatures, README.md, verifier and tests. Integrate both modules and run
powershell.exe -NoProfile -File ./verify.ps1 in the main checkout.
