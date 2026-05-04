# Sample Yoda conditions for testing — literal always on the LEFT side.

x = 5
s = "hello"
obj = None
flag = True
cond = False
count = 1
value = 5
val = 3
x_chain = 2
answer = 42
code = 0
items = [1, 2, 3]
maybe = None


class ObjWithProp:
    def __init__(self):
        self.prop = 'x'


obj_with_prop = ObjWithProp()

if 5 == x:
    print('numeric yoda')

if "hello" == s:
    print('string yoda')

# None == → should become `is None`
if None == obj:
    print('none yoda')

if True == flag:
    print('true yoda')
if False == cond:
    print('false yoda')

if 0 != count:
    print('not equal yoda')

if 10 < value:
    print('greater-than yoda')
if 3 >= val:
    print('less-or-equal yoda')

# chained — no auto-fix possible
if 1 < x_chain < 3:
    print('chained compare')

if 42 == answer and 0 != answer:
    print('combined')

result = 'ok' if 0 == code else 'fail'
print('ternary result:', result)


def check(a):
    if 7 == a:
        return True
    return False


print('check(7):', check(7))

# `1 in items` is NOT Yoda — swapping sides makes no sense for membership
if 1 in items:
    print('membership — not flagged')

if (100 == value) or (None == maybe):
    print('paren expression')

if 'x' == obj_with_prop.prop:
    print('attr compare')

# literal on right — must NOT be flagged
if count == 5:
    print('normal, not yoda')

if __name__ == '__main__':
    print('\n-- example.py execution finished --')
