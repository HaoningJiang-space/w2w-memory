def intermediate_partition(block, blocks, partitions):
    if blocks%partitions or not 0<=block<blocks: raise ValueError('Nonintegral partition')
    return block//(blocks//partitions)
