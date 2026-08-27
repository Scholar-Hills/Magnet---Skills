import sys


def first_at_least(nums, goal):
    """返回第一个不小于 goal 的下标（0 基）；一个都没有就返回 len(nums)。"""
    lo = 0
    hi = len(nums) - 1
    answer = len(nums)
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] >= goal:
            answer = mid          # 记下来，继续往左找更早的
            hi = mid - 1
        else:
            lo = mid + 1
    return answer


def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    goal = int(data[1 + n])

    idx = first_at_least(nums, goal)
    if idx == n:
        print("NONE")
    else:
        print(idx + 1)


main()
