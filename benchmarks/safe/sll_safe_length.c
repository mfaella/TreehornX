struct Node {
    int data;
    struct Node *next;
};

void sll_safe_length(struct Node **head) {
    struct Node *curr;
    int l;
    l = 0; //0
    curr = *head; //1
    while(curr != 0) { //2
        curr = curr->next; //3
        l = l + 1; //4
    }
}