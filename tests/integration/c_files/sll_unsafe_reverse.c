struct Node {
    int value;
    struct Node *next;
};    

void sll_unsafe_reverse(struct Node **head) {
    struct Node *x;
    struct Node *y;
    struct Node *tmp;

    x = *head;

    while(x != y) {
        tmp = x->next;
        x->next = y;
        y = x;
        x = tmp;
    }
}