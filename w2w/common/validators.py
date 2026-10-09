"""Scalar checks shared by native configuration and archived read schemas."""


def integer(value,name,minimum=0):
    if type(value) is not int or value<minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
