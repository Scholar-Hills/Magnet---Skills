import sys


def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    goal = int(data[1 + n])

    lo = 0
    hi = n - 1
    answer = n
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] >= goal:
            answer = mid
            hi = mid - 1
        else:
            lo = mid + 1

    if answer == n:
        print(0)
    else:
        print(answer + 1)


main()
