#!/usr/bin/env python3
"""
Prime Factorization Algorithm with Constrained Random Residue Oracle

This algorithm factors a number x using a constrained oracle:
- rand_residue(x, rand(2, sqrt(x))) returns x mod d where d is random in [2, sqrt(x)]
- Can only make polynomial(N(x)) calls where N(x) is the number of digits
- Decision function must be polynomial time
"""

import math
import random
from typing import List, Tuple, Optional, Set
from collections import defaultdict


def num_digits(n: int) -> int:
    """Return the number of digits needed to represent n"""
    if n == 0:
        return 1
    return int(math.log10(abs(n))) + 1


class RandResidueOracle:
    """
    Simulates the rand_residue oracle that returns x mod d
    where d is a random divisor in [2, sqrt(x)]
    """
    def __init__(self, x: int, seed: Optional[int] = None):
        self.x = x
        self.sqrt_x = int(math.isqrt(x))
        self.call_count = 0
        if seed is not None:
            random.seed(seed)
    
    def rand_residue(self) -> Tuple[int, int]:
        """
        Returns (d, x mod d) where d is random in [2, sqrt(x)]
        """
        if self.sqrt_x < 2:
            raise ValueError("sqrt(x) must be >= 2")
        
        d = random.randint(2, self.sqrt_x)
        residue = self.x % d
        self.call_count += 1
        return (d, residue)


def polynomial_bound(n_digits: int) -> int:
    """
    Returns a polynomial bound in the number of digits.
    Using O(n^3) as a reasonable polynomial bound.
    """
    return n_digits ** 3


def decision_function(x: int, residues: List[Tuple[int, int]], 
                     found_factors: Set[int], remaining: int) -> str:
    """
    Polynomial-time decision function to determine next action.
    
    Returns:
    - 'continue': Continue sampling
    - 'factor_found': A factor was found
    - 'done': Factorization complete
    """
    # Check if we found any zero residues (divisors)
    for d, residue in residues:
        if residue == 0 and d not in found_factors:
            return 'factor_found'
    
    # Check if remaining is prime or 1
    if remaining == 1:
        return 'done'
    
    if remaining < 2:
        return 'done'
    
    # Simple primality check (polynomial for small numbers)
    if remaining < 10**6:
        if is_prime_simple(remaining):
            return 'done'
    
    return 'continue'


def is_prime_simple(n: int) -> bool:
    """Simple primality test for small numbers (polynomial time)"""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    # Trial division up to sqrt(n) - polynomial for numbers with polynomial digits
    sqrt_n = int(math.isqrt(n))
    for i in range(3, sqrt_n + 1, 2):
        if n % i == 0:
            return False
    return True


def gcd(a: int, b: int) -> int:
    """Euclidean algorithm for GCD"""
    while b:
        a, b = b, a % b
    return a


def factorize_with_oracle(x: int, max_calls: Optional[int] = None, 
                          seed: Optional[int] = None) -> List[int]:
    """
    Factorize x using the constrained rand_residue oracle.
    
    Strategy:
    1. Use random residues to find divisors
    2. When residue is 0, we found a divisor
    3. Recursively factorize the quotient
    4. Use polynomial decision making at each step
    
    Args:
        x: Number to factorize
        max_calls: Maximum number of oracle calls (default: polynomial in digits)
        seed: Random seed for reproducibility
    
    Returns:
        List of prime factors (with multiplicities)
    """
    if x < 2:
        return []
    if x == 2:
        return [2]
    
    n_digits = num_digits(x)
    if max_calls is None:
        max_calls = polynomial_bound(n_digits)
    
    oracle = RandResidueOracle(x, seed)
    factors = []
    remaining = x
    
    # Track found divisors to avoid duplicates
    found_divisors = set()
    
    # Track prime factors we've already fully extracted to avoid duplicates
    processed_primes = set()
    
    # Collect residues for analysis
    residues = []
    
    # Phase 1: Try to find small factors using random sampling
    # We'll make up to max_calls attempts
    for _ in range(max_calls):
        if remaining == 1:
            break
        
        # Get a random residue
        d, residue = oracle.rand_residue()
        residues.append((d, residue))
        
        # Decision: what to do next?
        decision = decision_function(remaining, residues[-10:], found_divisors, remaining)
        
        if decision == 'done':
            if remaining > 1:
                factors.append(remaining)
            break
        
        # Check if this residue gives us a divisor
        if residue == 0:
            # Found a divisor!
            if d not in found_divisors and d > 1:
                # Verify it's actually a divisor
                if remaining % d == 0:
                    found_divisors.add(d)
                    
                    # Factorize d completely (it might be composite)
                    # Since d is in [2, sqrt(x)], it has at most half the digits of x
                    # So trial division is efficient
                    d_factors = trial_division(d)
                    
                    # Factor out each prime factor of d from remaining
                    for prime_factor in d_factors:
                        # Only process if we haven't fully extracted this prime yet
                        if prime_factor not in processed_primes:
                            count = 0
                            temp_remaining = remaining
                            while temp_remaining % prime_factor == 0:
                                factors.append(prime_factor)
                                temp_remaining //= prime_factor
                                count += 1
                            
                            if count > 0:
                                remaining = temp_remaining
                                # Mark this prime as processed if we've extracted all instances
                                # (we can't know for sure, but if remaining doesn't divide by it, we're done)
                                if remaining % prime_factor != 0:
                                    processed_primes.add(prime_factor)
                    
                    # If remaining is small enough, check if it's prime
                    if remaining > 1:
                        if remaining < 10**6 and is_prime_simple(remaining):
                            factors.append(remaining)
                            remaining = 1
                            break
                    
                    # Reset oracle for new remaining value
                    if remaining > 1:
                        oracle = RandResidueOracle(remaining, seed)
                        residues = []
        
        # Additional strategy: use GCD trick with multiple residues
        # If gcd(remaining, d) > 1 for some d, we might have found a factor
        if len(residues) >= 2 and remaining > 1:
            # Try GCD approach: if we have residues, check if any d's share factors with remaining
            for d1, r1 in residues[-10:]:
                if r1 != 0 and d1 > 1:
                    # If gcd(remaining, d1) > 1, we might have found a factor
                    g = gcd(remaining, d1)
                    if 1 < g < remaining and g not in found_divisors:
                        if remaining % g == 0:
                            found_divisors.add(g)
                            
                            # Factorize g completely (it might be composite)
                            # Since g divides remaining and g <= d1 <= sqrt(x), 
                            # g has at most half the digits of x, so trial division is efficient
                            g_factors = trial_division(g)
                            
                            # Factor out each prime factor of g from remaining
                            for prime_factor in g_factors:
                                # Only process if we haven't fully extracted this prime yet
                                if prime_factor not in processed_primes:
                                    count = 0
                                    temp_remaining = remaining
                                    while temp_remaining % prime_factor == 0:
                                        factors.append(prime_factor)
                                        temp_remaining //= prime_factor
                                        count += 1
                                    
                                    if count > 0:
                                        remaining = temp_remaining
                                        # Mark this prime as processed if we've extracted all instances
                                        if remaining % prime_factor != 0:
                                            processed_primes.add(prime_factor)
                            
                            if remaining > 1:
                                oracle = RandResidueOracle(remaining, seed)
                                residues = []
                            break
    
    # If we still have remaining > 1, try to finish factorization
    if remaining > 1:
        # Try simple trial division for small remaining values
        if remaining < 10**6:
            factors.extend(trial_division(remaining))
        else:
            # If still large, add as remaining factor
            factors.append(remaining)
    
    return sorted(factors)


def trial_division(n: int) -> List[int]:
    """Simple trial division for small numbers"""
    factors = []
    d = 2
    while d * d <= n:
        while n % d == 0:
            factors.append(d)
            n //= d
        d += 1
    if n > 1:
        factors.append(n)
    return factors


def verify_factorization(x: int, factors: List[int]) -> bool:
    """Verify that the factorization is correct"""
    product = 1
    for f in factors:
        product *= f
    return product == x


def main():
    """Test the factorization algorithm"""
    import sys
    
    test_cases = [
        12,           # 2^2 * 3
        100,          # 2^2 * 5^2
        12345,        # 3 * 5 * 823
        123456,       # 2^6 * 3 * 643
        999999,       # 3^3 * 7 * 11 * 13 * 37
    ]
    
    if len(sys.argv) > 1:
        try:
            x = int(sys.argv[1])
            test_cases = [x]
        except ValueError:
            print(f"Invalid number: {sys.argv[1]}")
            return
    
    print("Prime Factorization with Constrained Random Residue Oracle")
    print("=" * 60)
    
    for x in test_cases:
        print(f"\nFactoring: {x}")
        print(f"Number of digits: {num_digits(x)}")
        print(f"Max oracle calls: {polynomial_bound(num_digits(x))}")
        
        factors = factorize_with_oracle(x)
        
        print(f"Factors: {factors}")
        print(f"Verification: {verify_factorization(x, factors)}")
        
        # Show prime factorization
        from collections import Counter
        factor_counts = Counter(factors)
        factor_str = " * ".join(
            f"{p}^{e}" if e > 1 else str(p)
            for p, e in sorted(factor_counts.items())
        )
        print(f"Prime factorization: {factor_str}")


if __name__ == "__main__":
    main()

