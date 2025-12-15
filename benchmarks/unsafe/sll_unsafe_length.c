struct Node {
    int data;
    struct Node *next;
};

void sll_unsafe_length(struct Node **head) {
    struct Node *curr;
    struct Node *next;
    int l;
    l = 0; //0
    curr = *head; //1
    next = curr->next; //2
    while(next) { //3
        curr = curr->next; //4
        next = curr->next; //5
        l = l + 1; //6
    }
}