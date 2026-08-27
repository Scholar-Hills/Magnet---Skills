import sys


def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    goal = int(data[1 + n])

    lo = 0
    hi = n - 1
    found = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == goal:
            found = mid
            break
        elif nums[mid] < goal:
            lo = mid + 1
        else:
            hi = mid - 1

    if found == -1:
        print("NONE")
    else:
        print(found + 1)


main()
