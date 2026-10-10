"""Committed descriptor prefix; a bounded validity bitmap, not an OOO MAC design."""


class CommittedWeightPrefix:
    def __init__(self,data_bytes,fragment_bytes):
        self.data_bytes=data_bytes;self.fragment_bytes=fragment_bytes
        self.fragments=(data_bytes+fragment_bytes-1)//fragment_bytes
        self.mask=0;self.head=0
        self.metadata_bytes=(self.fragments+7)//8+8  # validity, 32-bit frontier, 32-bit association

    @property
    def ready_bytes(self):return min(self.data_bytes,self.head*self.fragment_bytes)

    def receive(self,offset,size):
        if (offset<0 or offset>=self.data_bytes or offset%self.fragment_bytes
                or size!=min(self.fragment_bytes,self.data_bytes-offset)):
            raise ValueError('Prefix policy requires committed canonical data descriptors')
        index=offset//self.fragment_bytes;bit=1<<index
        if self.mask&bit:raise ValueError('Weight fragment committed twice')
        self.mask|=bit
        while self.head<self.fragments and self.mask&(1<<self.head):self.head+=1

    def cached(self):
        self.mask=(1<<self.fragments)-1;self.head=self.fragments
