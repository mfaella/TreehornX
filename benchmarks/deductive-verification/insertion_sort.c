#include <stdio.h>
#include <stdlib.h>

// Node structure
struct Node {
    int data;
    struct Node* next;
    struct Node *parent;
};

void insertion_sort_iteration(struct Node* root, int i) {
    // precondition
    int j;
    int n;
    int curr_data;
    int tmp_data;
    struct Node *curr;
    struct Node *tmp;
    struct Node *prev;

    n = 0;
    curr = root;
    while(curr) {
        n = n + 1;
        curr->parent = tmp;
        tmp = curr;
        curr = curr->next;
    }
    if (i < 0 || i > n) {
        return;
    }

    // funzione
    curr = root;
    j = 0;
    while(j < n - i) {
        curr = curr->next;
        j = j + 1;
    }
    while(j < n) {
        curr_data = curr->data;
        tmp = curr->next;
        tmp_data = tmp->data;
        if(curr_data > tmp_data) {
            return;
        }
    }

    curr = root;
    j = 0;
    while(j < n - i - 1) {
        prev = curr;
        curr = curr->next;
    }

    while(curr) {
        curr_data = curr->data;
        tmp = curr->next;
        if(tmp) {
            tmp_data = tmp->data;
            if(curr_data > tmp_data) {
                if(prev) {
                    prev->next = tmp;
                    prev = curr;
                    curr = tmp;
                    tmp = curr->next;
                    prev->next = tmp;
                    curr->next = prev;

                    curr->next =
                }
            }

        }
        tmp
    }

}
