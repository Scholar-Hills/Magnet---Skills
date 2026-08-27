import sys


def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    goal = int(data[1 + n])

    # TODO: 算出第一个不小于 goal 的元素的位置（从 1 开始）；
    #       所有元素都小于 goal 时输出 NONE。
    #       下面这行是占位，请替换掉。
    print(-1)


main()
